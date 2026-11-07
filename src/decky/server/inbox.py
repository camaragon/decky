"""Explicitly scoped authored PR review and local decision delivery."""

import json
import re
import subprocess
from urllib.error import URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import click
from fastapi import APIRouter, HTTPException, Request as WebRequest
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Literal

from decky import config, github
from decky.commands.pr import image_urls
from decky.process import run_command

router = APIRouter(prefix="/api/inbox")


def owners(key: str = "review.owners") -> list[str]:
    values, _ = config.resolve(key)
    values = values or []
    if any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", v) for v in values):
        raise click.ClickException(f"{key} must contain GitHub owner names")
    return list(dict.fromkeys(v.lower() for v in values))


def owner_allowed(owner: str) -> bool:
    all_owners, _ = config.resolve("review.all_owners")
    return owner.lower() not in owners("review.exclude_owners") if all_owners else owner.lower() in owners()


def stacks(rows: list[dict]) -> list[dict]:
    result = []
    for repo in sorted({r["repo"] for r in rows}):
        remaining = {r["number"]: r for r in rows if r["repo"] == repo}
        heads = {r["head_branch"]: r["number"] for r in remaining.values() if not r["cross_repository"]}
        parents = {n: heads.get(r["base_branch"]) for n, r in remaining.items()}
        parents = {n: None if p == n else p for n, p in parents.items()}
        while remaining:
            root = min(remaining)
            seen = set()
            while parents[root] in remaining and parents[root] not in seen:
                seen.add(root)
                root = parents[root]
            ordered = []
            def visit(n):
                if n not in remaining:
                    return
                ordered.append(remaining.pop(n))
                for child in sorted(remaining.copy()):
                    if parents[child] == n:
                        visit(child)
            visit(root)
            result.append({"repo": repo, "prs": ordered})
    return result


def search(owner: str | None, repo: str | None = None) -> tuple[list[dict], list[str]]:
    rows, notes = [], []
    # GitHub issue search spells the owner qualifier `user:`, including organizations.
    excluded = owners("review.exclude_owners") if owner is None else []
    q = "is:pr is:open author:@me"
    q += f" user:{owner}" if owner is not None else "".join(f" -user:{value}" for value in excluded)
    q += f" repo:{repo}" if repo else ""
    cursor = None
    while True:
        query = '''query($q: String!, $cursor: String) {
          search(query: $q, type: ISSUE, first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes { ... on PullRequest { number repository { nameWithOwner } } }
          }
        }'''
        args = ["api", "graphql", "-f", f"query={query}", "-f", f"q={q}"]
        if cursor:
            args += ["-f", f"cursor={cursor}"]
        page = github._gh_json(*args)["data"]["search"]
        for node in page["nodes"]:
            slug = node["repository"]["nameWithOwner"]
            slug_owner = slug.split("/")[0].lower()
            if slug_owner in excluded or (owner is not None and slug_owner != owner) or (repo and slug.lower() != repo.lower()):
                continue
            row, warnings = github.load_pr(slug, node["number"])
            row_owner = row["repo"].split("/")[0].lower()
            if row_owner in excluded or (owner is not None and row_owner != owner):
                continue
            row["image_urls"] = image_urls(row["body"])
            rows.append(row)
            notes.extend(warnings)
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return rows, notes


def load() -> dict:
    configured = owners()
    rows, notes = [], []
    all_owners, _ = config.resolve("review.all_owners")
    for owner in ([None] if all_owners else configured):
        found, warnings = search(owner)
        rows += found
        notes += warnings
    command, _ = config.resolve("review.decision_command")
    return {"owners": configured, "stacks": stacks(rows), "notes": list(dict.fromkeys(notes)), "decision_enabled": bool(command)}


@router.get("")
def inbox(request: WebRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    data = load()
    with request.app.state.decky.lock:
        request.app.state.decky.inbox_rows = {(p["repo"], p["number"]): p for s in data["stacks"] for p in s["prs"]}
    return data


class Answer(BaseModel):
    decision: Literal["merge", "hold"]
    scope: Literal["pr", "stack"]
    repo: str = Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9._-]+$")
    numbers: list[int] = Field(min_length=1)
    head_shas: list[str]
    note: str = Field(default="", max_length=10000)


@router.post("/decision")
def decision(answer: Answer, request: WebRequest):
    command, _ = config.resolve("review.decision_command")
    if not command:
        raise HTTPException(409, "Configure review.decision_command to send answers")
    owner = answer.repo.split("/")[0].lower()
    if not owner_allowed(owner):
        raise HTTPException(403, "Repository owner is not allowed by review settings")
    all_owners, _ = config.resolve("review.all_owners")
    rows, _ = search(None if all_owners else owner, answer.repo)
    selected = None
    for stack in stacks(rows):
        if stack["repo"] != answer.repo:
            continue
        candidates = stack["prs"] if answer.scope == "stack" else [p for p in stack["prs"] if p["number"] in answer.numbers]
        if [p["number"] for p in candidates] == answer.numbers:
            selected = candidates
            break
    if not selected or (answer.scope == "pr" and len(selected) != 1):
        raise HTTPException(409, "PR selection changed; refresh the inbox")
    if [p["head_sha"] for p in selected] != answer.head_shas:
        raise HTTPException(409, "PR commits changed; refresh and review again")
    payload = {"version": 1, "decision": answer.decision, "scope": answer.scope, "repo": answer.repo,
               "prs": [{"number": p["number"], "url": p["url"], "head_sha": p["head_sha"]} for p in selected], "note": answer.note}
    try:
        result = run_command(command, "review.decision_command", input=json.dumps(payload), text=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Decision command timed out; delivery is uncertain") from None
    if result.returncode:
        raise HTTPException(422, f"Decision command exited {result.returncode}")
    return {"message": "Answer delivered", "decision": answer.decision}


IMAGE_HOSTS = {"raw.githubusercontent.com", "github.com", "user-images.githubusercontent.com", "private-user-images.githubusercontent.com", "camo.githubusercontent.com", "objects.githubusercontent.com"}


def safe_image(url: str) -> bool:
    try:
        p = urlsplit(url)
        return p.scheme == "https" and p.hostname in IMAGE_HOSTS and not p.username and not p.password and p.port in (None, 443)
    except ValueError:
        return False


def image_sources(url: str, repo: str) -> list[str]:
    p = urlsplit(url)
    parts = unquote(p.path).strip("/").split("/")
    if p.hostname == "raw.githubusercontent.com":
        offset = 2
    elif p.hostname == "github.com" and len(parts) > 2 and parts[2] in {"blob", "raw"}:
        offset = 3
    else:
        return [url]
    if "/".join(parts[:2]).lower() != repo.lower() or len(parts) < offset + 2 or any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(403, "Image is not a file in the PR repository")
    # Try longer refs first because branch names can contain slashes.
    return [f"https://api.github.com/repos/{quote(repo, safe='/')}/contents/{quote('/'.join(parts[split:]), safe='/')}?"
            + urlencode({"ref": "/".join(parts[offset:split])})
            for split in range(len(parts) - 1, offset, -1)]


def raster_kind(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    return None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@router.get("/image")
def image(request: WebRequest, repo: str, number: int, url: str):
    from urllib.error import HTTPError
    with request.app.state.decky.lock:
        row = request.app.state.decky.inbox_rows.get((repo, number))
    if not owner_allowed(repo.split("/")[0]) or not row or url not in row["image_urls"] or not safe_image(url):
        raise HTTPException(403, "Image is not an allowed PR attachment")
    image_sources(url, repo)
    token = github.run_gh("auth", "token", "--hostname", "github.com")
    if token.returncode:
        raise HTTPException(502, "GitHub credentials unavailable")
    opener = build_opener(NoRedirect())
    try:
        for _ in range(5):
            if not safe_image(url):
                raise HTTPException(403, "Image redirect host is not allowed")
            try:
                sources = image_sources(url, repo)
                for index, source in enumerate(sources):
                    headers = {"Authorization": f"Bearer {token.stdout.strip()}"}
                    if source != url:
                        headers["Accept"] = "application/vnd.github.raw"
                    try:
                        upstream = opener.open(Request(source, headers=headers), timeout=15)
                        break
                    except HTTPError as error:
                        if error.code != 404 or index == len(sources) - 1:
                            raise
                        error.close()
            except HTTPError as error:
                if error.code in (301, 302, 303, 307, 308):
                    url = error.headers.get("Location", "")
                    continue
                raise
            with upstream:
                content = upstream.read(10 * 1024 * 1024 + 1)
                kind = raster_kind(content) if source != url else upstream.headers.get_content_type()
            if kind not in {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"}:
                raise HTTPException(415, "Unsupported image type")
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(413, "Image exceeds 10 MiB")
            return Response(content, media_type=kind, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
    except (URLError, OSError):
        raise HTTPException(502, "Could not fetch GitHub image") from None
    raise HTTPException(502, "Too many image redirects")

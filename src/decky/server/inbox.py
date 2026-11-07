"""Explicitly scoped authored PR review and local decision delivery."""

import json
import re
import subprocess
from urllib.error import URLError
from urllib.parse import urlsplit
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


def owners() -> list[str]:
    values, _ = config.resolve("review.owners")
    values = values or []
    if any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", v) for v in values):
        raise click.ClickException("review.owners must contain GitHub owner names")
    return list(dict.fromkeys(v.lower() for v in values))


def stacks(rows: list[dict]) -> list[dict]:
    result = []
    for repo in sorted({r["repo"] for r in rows}):
        remaining = {r["number"]: r for r in rows if r["repo"] == repo}
        heads = {r["head_branch"]: r["number"] for r in remaining.values()}
        parents = {n: heads.get(r["base_branch"]) for n, r in remaining.items()}
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


def load() -> dict:
    configured = owners()
    rows, notes = [], []
    for owner in configured:
        # GitHub issue search spells the owner qualifier `user:`, including organizations.
        cursor = None
        while True:
            query = '''query($q: String!, $cursor: String) {
              search(query: $q, type: ISSUE, first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes { ... on PullRequest { number repository { nameWithOwner } } }
              }
            }'''
            args = ["api", "graphql", "-f", f"query={query}", "-f", f"q=is:pr is:open author:@me user:{owner}"]
            if cursor:
                args += ["-f", f"cursor={cursor}"]
            page = github._gh_json(*args)["data"]["search"]
            for node in page["nodes"]:
                repo = node["repository"]["nameWithOwner"]
                if repo.split("/")[0].lower() != owner:
                    continue
                row, warnings = github.load_pr(repo, node["number"])
                if row["repo"].split("/")[0].lower() != owner:
                    continue
                row["image_urls"] = image_urls(row["body"])
                rows.append(row)
                notes.extend(warnings)
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
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
    repo: str
    numbers: list[int] = Field(min_length=1)
    head_shas: list[str]
    note: str = Field(default="", max_length=10000)


@router.post("/decision")
def decision(answer: Answer, request: WebRequest):
    command, _ = config.resolve("review.decision_command")
    if not command:
        raise HTTPException(409, "Configure review.decision_command to send answers")
    data = load()
    selected = None
    for stack in data["stacks"]:
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


IMAGE_HOSTS = {"github.com", "user-images.githubusercontent.com", "private-user-images.githubusercontent.com", "camo.githubusercontent.com", "objects.githubusercontent.com"}


def safe_image(url: str) -> bool:
    try:
        p = urlsplit(url)
        return p.scheme == "https" and p.hostname in IMAGE_HOSTS and not p.username and not p.password and p.port in (None, 443)
    except ValueError:
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@router.get("/image")
def image(request: WebRequest, repo: str, number: int, url: str):
    from urllib.error import HTTPError
    with request.app.state.decky.lock:
        row = request.app.state.decky.inbox_rows.get((repo, number))
    if repo.split("/")[0].lower() not in owners() or not row or url not in row["image_urls"] or not safe_image(url):
        raise HTTPException(403, "Image is not an allowed PR attachment")
    token = github.run_gh("auth", "token", "--hostname", "github.com")
    if token.returncode:
        raise HTTPException(502, "GitHub credentials unavailable")
    opener = build_opener(NoRedirect())
    try:
        for _ in range(5):
            if not safe_image(url):
                raise HTTPException(403, "Image redirect host is not allowed")
            try:
                upstream = opener.open(Request(url, headers={"Authorization": f"Bearer {token.stdout.strip()}"}), timeout=15)
            except HTTPError as error:
                if error.code in (301, 302, 303, 307, 308):
                    url = error.headers.get("Location", "")
                    continue
                raise
            with upstream:
                kind = upstream.headers.get_content_type()
                if kind not in {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"}:
                    raise HTTPException(415, "Unsupported image type")
                content = upstream.read(10 * 1024 * 1024 + 1)
                if len(content) > 10 * 1024 * 1024:
                    raise HTTPException(413, "Image exceeds 10 MiB")
                return Response(content, media_type=kind, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
    except (URLError, OSError):
        raise HTTPException(502, "Could not fetch GitHub image") from None
    raise HTTPException(502, "Too many image redirects")

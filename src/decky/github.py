"""GitHub access via the gh CLI."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import click

from decky import config

RETRY_DELAYS = (2, 4, 8, 16)
RETRYABLE = (
    "rate limit",
    "too quickly",
    "http 502",
    "http 503",
    "http 504",
    "unexpected end of json input",
)

CHECK_STATES = {
    "SUCCESS": "pass",
    "FAILURE": "fail",
    "ERROR": "fail",
    "PENDING": "pending",
    "EXPECTED": "pending",
}

MAX_WATCH = 15

PR_FIELDS = """
fragment PrFields on PullRequest {
  number
  title
  isDraft
  updatedAt
  author { login }
  repository { nameWithOwner }
  commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
  latestOpinionatedReviews(first: 20) { nodes { state } }
  reviewRequests(first: 20) {
    pageInfo { hasNextPage }
    nodes { requestedReviewer { ... on User { login } ... on Team { slug } } }
  }
}
"""

SEARCH_NODES = """
    pageInfo { hasNextPage }
    nodes { ... on PullRequest { ...PrFields } }
"""


def _list_setting(key: str) -> list[str]:
    value, _ = config.resolve(key)
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _escape_query(q: str) -> str:
    return q.replace("\\", "\\\\").replace('"', '\\"')


def build_graphql(watch_teams: list[str], watch_repos: list[str]) -> str:
    extra = ""
    for i, team in enumerate(watch_teams[:MAX_WATCH]):
        q = _escape_query(f"is:pr is:open archived:false team-review-requested:{team}")
        extra += f"""
  watchTeam{i}: search(query: "{q}", type: ISSUE, first: 50) {{{SEARCH_NODES}
  }}"""
    for i, repo in enumerate(watch_repos[:MAX_WATCH]):
        q = _escape_query(
            f"repo:{repo} is:pr is:open archived:false -author:@me -reviewed-by:@me"
        )
        extra += f"""
  watchRepo{i}: search(query: "{q}", type: ISSUE, first: 50) {{{SEARCH_NODES}
  }}"""
    return f"""
{PR_FIELDS}

query DeckyPrLists {{
  viewer {{
    login
    pullRequests(first: 50, states: OPEN) {{
      pageInfo {{ hasNextPage }}
      nodes {{ ...PrFields }}
    }}
  }}
  reviewSearch: search(
    query: "is:pr is:open archived:false review-requested:@me"
    type: ISSUE
    first: 50
  ) {{{SEARCH_NODES}
  }}{extra}
}}
"""


def same_login(a: str, b: str) -> bool:
    return a.lower().removesuffix("[bot]") == b.lower().removesuffix("[bot]")


def retryable(result: subprocess.CompletedProcess[str]) -> bool:
    output = f"{result.stderr or ''} {result.stdout or ''}".lower()
    return any(marker in output for marker in RETRYABLE)


def run_gh(*args: str) -> subprocess.CompletedProcess[str]:
    for delay in (*RETRY_DELAYS, None):
        try:
            result = subprocess.run(
                ["gh", *args], capture_output=True, text=True, check=False
            )
        except FileNotFoundError:
            raise click.ClickException("gh not found; install the GitHub CLI") from None
        if result.returncode == 0 or delay is None or not retryable(result):
            return result
        time.sleep(delay)
    raise AssertionError("unreachable")


def pr_from_node(node: dict[str, Any]) -> dict[str, Any]:
    commits = (node.get("commits") or {}).get("nodes") or []
    rollup = commits[0]["commit"]["statusCheckRollup"] if commits else None
    state = rollup.get("state") if rollup else None
    reviews = (node.get("latestOpinionatedReviews") or {}).get("nodes") or []
    return {
        "number": node["number"],
        "repo": node["repository"]["nameWithOwner"],
        "title": node["title"],
        "checks": CHECK_STATES.get(state, "none"),
        "approvals": sum(1 for r in reviews if r and r.get("state") == "APPROVED"),
        "draft": bool(node.get("isDraft")),
        "author": (node.get("author") or {}).get("login") or "",
        "updated_at": node.get("updatedAt") or "",
        "review_requests_truncated": bool(
            ((node.get("reviewRequests") or {}).get("pageInfo") or {}).get(
                "hasNextPage"
            )
        ),
    }


def _classify_review(node: dict[str, Any], viewer_login: str) -> str | None:
    """Return review, team, or None if this search node is not a review request for viewer."""
    requests = (node.get("reviewRequests") or {}).get("nodes") or []
    user_match = False
    team_match = False
    for req in requests:
        reviewer = (req or {}).get("requestedReviewer") or {}
        login = reviewer.get("login")
        if login and same_login(login, viewer_login):
            user_match = True
        if reviewer.get("slug"):
            team_match = True
    if user_match:
        return "review"
    if team_match:
        return "team"
    return None


def _note_truncation(notes: list[str], page_info: dict[str, Any] | None) -> None:
    if (page_info or {}).get("hasNextPage"):
        note = "list truncated at GitHub page size"
        if note not in notes:
            notes.append(note)


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    return (row["repo"], row["number"])


def load_pr_lists() -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Load review, team, and mine lists; return notes for truncation."""
    watch_teams = _list_setting("pr.watch_teams")
    watch_repos = _list_setting("pr.watch_repos")
    query = build_graphql(watch_teams, watch_repos)
    result = run_gh("api", "graphql", "-f", f"query={query}")
    if result.returncode != 0:
        raise click.ClickException(f"gh api graphql failed: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)["data"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise click.ClickException(
            "gh returned unreadable pull request lists"
        ) from None

    viewer = data["viewer"]
    login = viewer["login"]
    notes: list[str] = []

    mine_page = (viewer.get("pullRequests") or {}).get("pageInfo") or {}
    _note_truncation(notes, mine_page)
    search_page = (data.get("reviewSearch") or {}).get("pageInfo") or {}
    _note_truncation(notes, search_page)

    mine_nodes = (viewer.get("pullRequests") or {}).get("nodes") or []
    mine = [pr_from_node(n) for n in mine_nodes if n]
    if any(p.pop("review_requests_truncated", False) for p in mine):
        _note_truncation(notes, {"hasNextPage": True})

    review: list[dict[str, Any]] = []
    team: list[dict[str, Any]] = []
    review_keys: set[tuple[str, int]] = set()
    team_keys: set[tuple[str, int]] = set()

    def add_row(row: dict[str, Any], bucket: str) -> None:
        key = _row_key(row)
        truncated = row.pop("review_requests_truncated", False)
        if truncated:
            _note_truncation(notes, {"hasNextPage": True})
        if bucket == "review":
            if key in review_keys:
                return
            review_keys.add(key)
            team_keys.discard(key)
            team[:] = [p for p in team if _row_key(p) != key]
            review.append(row)
        else:
            if key in review_keys:
                return
            if key in team_keys:
                return
            team_keys.add(key)
            team.append(row)

    for node in (data.get("reviewSearch") or {}).get("nodes") or []:
        if not node:
            continue
        row = pr_from_node(node)
        kind = _classify_review(node, login)
        if kind == "review":
            add_row(row, "review")
        elif kind == "team":
            add_row(row, "team")

    for i, _team in enumerate(watch_teams[:MAX_WATCH]):
        block = data.get(f"watchTeam{i}") or {}
        _note_truncation(notes, block.get("pageInfo"))
        for node in block.get("nodes") or []:
            if not node:
                continue
            row = pr_from_node(node)
            kind = _classify_review(node, login)
            if kind == "review":
                add_row(row, "review")
            else:
                add_row(row, "team")

    for i, _repo in enumerate(watch_repos[:MAX_WATCH]):
        block = data.get(f"watchRepo{i}") or {}
        _note_truncation(notes, block.get("pageInfo"))
        for node in block.get("nodes") or []:
            if not node:
                continue
            row = pr_from_node(node)
            if same_login(row["author"], login):
                continue
            add_row(row, "review")

    sort_key = lambda pr: (pr["repo"], pr["number"])
    return (
        {
            "review": sorted(review, key=sort_key),
            "team": sorted(team, key=sort_key),
            "mine": sorted(mine, key=sort_key),
        },
        notes,
    )


def clone(slug: str, dest: Path) -> None:
    cmd = [
        "gh",
        "repo",
        "clone",
        f"github.com/{slug}",
        str(dest),
        "--",
        "--recurse-submodules",
    ]
    try:
        code = subprocess.run(cmd, check=False).returncode
    except FileNotFoundError:
        raise click.ClickException("gh not found; install the GitHub CLI") from None
    if code != 0:
        raise click.ClickException(
            f"could not clone {slug} into {dest} (gh exit {code}); "
            f"run `gh auth status`, confirm Git access to {slug} and its submodules, "
            f"and remove {dest} if a partial checkout remains"
        )


def remote_matches(dest: Path, slug: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    url = result.stdout.strip()
    if "://" in url:
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"https", "ssh"} or parsed.query or parsed.fragment:
                return False
            host = parsed.hostname
            path = parsed.path.removeprefix("/")
        except ValueError:
            return False
    else:
        match = re.fullmatch(r"(?:[^@/\s]+@)?([^:/\s]+):([^?#\s]+)", url)
        if not match:
            return False
        host, path = match.groups()
    return (
        host is not None
        and host.lower() == "github.com"
        and path.lower().removesuffix(".git") == slug.lower()
    )


def clone_or_reuse(slug: str, dest: Path) -> None:
    if dest.exists():
        if remote_matches(dest, slug):
            click.echo(f"using existing checkout {dest}")
            return
        raise click.ClickException(f"{dest} exists and is not {slug}")
    clone(slug, dest)


def repo_slug(name: str, org: str | None) -> str:
    if "/" in name:
        return name
    if not org:
        raise click.UsageError("bare repo name requires work_org")
    return f"{org}/{name}"

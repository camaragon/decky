"""GitHub access via the gh CLI."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import click

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

GRAPHQL = """
fragment PrFields on PullRequest {
  number
  title
  isDraft
  author { login }
  repository { nameWithOwner }
  commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
  latestOpinionatedReviews(first: 20) { nodes { state } }
  reviewRequests(first: 20) {
    pageInfo { hasNextPage }
    nodes { requestedReviewer { ... on User { login } ... on Team { slug } } }
  }
}

query DeckyPrLists {
  viewer {
    login
    pullRequests(first: 50, states: OPEN) {
      pageInfo { hasNextPage }
      nodes { ...PrFields }
    }
  }
  reviewSearch: search(
    query: "is:pr is:open archived:false review-requested:@me"
    type: ISSUE
    first: 50
  ) {
    pageInfo { hasNextPage }
    nodes { ... on PullRequest { ...PrFields } }
  }
}
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
        "review_requests_truncated": bool(
            ((node.get("reviewRequests") or {}).get("pageInfo") or {}).get("hasNextPage")
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


def load_pr_lists() -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Load review, team, and mine lists; return notes for truncation."""
    result = run_gh("api", "graphql", "-f", f"query={GRAPHQL}")
    if result.returncode != 0:
        raise click.ClickException(f"gh api graphql failed: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)["data"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise click.ClickException("gh returned unreadable pull request lists") from None

    viewer = data["viewer"]
    login = viewer["login"]
    notes: list[str] = []

    mine_page = (viewer.get("pullRequests") or {}).get("pageInfo") or {}
    if mine_page.get("hasNextPage"):
        notes.append("list truncated at GitHub page size")
    search_page = (data.get("reviewSearch") or {}).get("pageInfo") or {}
    if search_page.get("hasNextPage"):
        notes.append("list truncated at GitHub page size")

    mine_nodes = (viewer.get("pullRequests") or {}).get("nodes") or []
    mine = [pr_from_node(n) for n in mine_nodes if n]
    if any(p.pop("review_requests_truncated", False) for p in mine):
        notes.append("list truncated at GitHub page size")

    review: list[dict[str, Any]] = []
    team: list[dict[str, Any]] = []
    for node in (data.get("reviewSearch") or {}).get("nodes") or []:
        if not node:
            continue
        row = pr_from_node(node)
        if row.pop("review_requests_truncated", False):
            notes.append("list truncated at GitHub page size")
        kind = _classify_review(node, login)
        if kind == "review":
            review.append(row)
        elif kind == "team":
            team.append(row)

    sort_key = lambda pr: (pr["repo"], pr["number"])
    return (
        {
            "review": sorted(review, key=sort_key),
            "team": sorted(team, key=sort_key),
            "mine": sorted(mine, key=sort_key),
        },
        notes,
    )


def clone(slug: str, dest: Path) -> int:
    cmd = ["git", "clone", "--recurse-submodules", f"git@github.com:{slug}.git", str(dest)]
    return subprocess.run(cmd).returncode


def remote_matches(dest: Path, slug: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    url = result.stdout.strip().lower().removesuffix(".git")
    slug = slug.lower()
    return url.endswith(f":{slug}") or url.endswith(f"/{slug}")


def clone_or_reuse(slug: str, dest: Path) -> None:
    if dest.exists():
        if remote_matches(dest, slug):
            click.echo(f"using existing checkout {dest}")
            return
        raise click.ClickException(f"{dest} exists and is not {slug}")
    code = clone(slug, dest)
    if code != 0:
        raise click.exceptions.Exit(code)


def repo_slug(name: str, org: str | None) -> str:
    if "/" in name:
        return name
    if not org:
        raise click.UsageError("bare repo name requires work_org")
    return f"{org}/{name}"

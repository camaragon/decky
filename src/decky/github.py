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

LIST_TRUNCATED = "list truncated at GitHub page size"

TRUNCATION_NOTES = (
    ("reviewRequests", LIST_TRUNCATED),
    ("labels", "labels truncated at 100"),
    ("latestOpinionatedReviews", "approvals may be partial (20 latest reviews)"),
)

DETAIL_FIELDS = """
  url
  body
  reviewDecision
  labels(first: 100) { pageInfo { hasNextPage } nodes { name } }
  latestOpinionatedReviews(first: 20) { pageInfo { hasNextPage } }"""

PR_FIELDS = """
fragment PrFields on PullRequest {
  number
  title%s
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


def build_graphql(
    watch_teams: list[str],
    watch_repos: list[str],
    watch_owners: list[str] | None = None,
    details: bool = False,
) -> str:
    extra = ""
    for i, team in enumerate(watch_teams[:MAX_WATCH]):
        q = _escape_query(f"is:pr is:open archived:false team-review-requested:{team}")
        extra += f"""
  watchTeam{i}: search(query: "{q}", type: ISSUE, first: 50) {{{SEARCH_NODES}
  }}"""
    for source, qualifier, values in (
        ("Repo", "repo", watch_repos),
        ("Owner", "user", watch_owners or []),
    ):
        for i, value in enumerate(values[:MAX_WATCH]):
            q = _escape_query(
                f"{qualifier}:{value} is:pr is:open archived:false -author:@me -reviewed-by:@me"
            )
            extra += f"""
  watch{source}{i}: search(query: "{q}", type: ISSUE, first: 50) {{{SEARCH_NODES}
  }}"""
    fields = PR_FIELDS % (DETAIL_FIELDS if details else "")
    return f"""
{fields}

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


def pr_from_node(node: dict[str, Any], details: bool = False) -> dict[str, Any]:
    commits = (node.get("commits") or {}).get("nodes") or []
    rollup = commits[0]["commit"]["statusCheckRollup"] if commits else None
    state = rollup.get("state") if rollup else None
    reviews = (node.get("latestOpinionatedReviews") or {}).get("nodes") or []
    slug = node["repository"]["nameWithOwner"]
    row = {
        "number": node["number"],
        "repo": slug,
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
        "truncation_notes": [
            note
            for field, note in TRUNCATION_NOTES
            if details
            and field != "reviewRequests"
            and ((node.get(field) or {}).get("pageInfo") or {}).get("hasNextPage")
        ],
    }
    if details:
        owner, name = slug.split("/", 1)
        row.update(
            repo_owner=owner,
            repo_name=name,
            url=node.get("url") or f"https://github.com/{slug}/pull/{node['number']}",
            body=node.get("body") or "",
            review_decision=node.get("reviewDecision"),
            labels=[
                label["name"] for label in (node.get("labels") or {}).get("nodes", [])
            ],
        )
    return row


def _gh_json(*args: str) -> Any:
    result = run_gh(*args)
    if result.returncode:
        operation = "api graphql" if args[:2] == ("api", "graphql") else "request"
        raise click.ClickException(f"gh {operation} failed: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise click.ClickException("gh returned unreadable JSON") from None
    if isinstance(payload, dict) and payload.get("errors"):
        raise click.ClickException(f"GitHub errors: {payload['errors']}")
    return payload


def load_pr(slug: str, number: int) -> tuple[dict[str, Any], list[str]]:
    owner, repo = slug.split("/")
    query = (
        (PR_FIELDS % DETAIL_FIELDS)
        + """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) { ...PrFields changedFiles headRefOid headRefName baseRefName }
  }
}
"""
    )
    data = _gh_json(
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-f",
        f"owner={owner}",
        "-f",
        f"repo={repo}",
        "-F",
        f"number={number}",
    )["data"]
    node = (data.get("repository") or {}).get("pullRequest")
    if not node:
        raise click.ClickException("pull request not found or inaccessible")
    row = pr_from_node(node, details=True)
    row.update(head_sha=node["headRefOid"], head_branch=node.get("headRefName", ""), base_branch=node.get("baseRefName", ""))
    notes: list[str] = []
    if row.pop("review_requests_truncated", False):
        _add_note(notes, "review requests truncated at 20")
    _take_notes(notes, row)
    files = _gh_json(
        "api",
        f"repos/{slug}/pulls/{number}/files?per_page=100",
        "--paginate",
        "--slurp",
    )
    row["files"] = [
        {
            "path": f["filename"],
            "additions": f["additions"],
            "deletions": f["deletions"],
        }
        for page in files
        for f in page
    ]
    row["changed_files"] = node["changedFiles"]
    if len(row["files"]) < row["changed_files"]:
        notes.append("changed files truncated by GitHub (maximum 3000)")
    commit = f"repos/{slug}/commits/{node['headRefOid']}"
    runs = _gh_json("api", f"{commit}/check-runs?per_page=100", "--paginate", "--slurp")
    statuses = _gh_json("api", f"{commit}/status?per_page=100", "--paginate", "--slurp")
    row["check_runs"] = [
        {
            "name": c["name"],
            "status": c["status"],
            "conclusion": c["conclusion"],
            "url": c["html_url"],
        }
        for page in runs
        for c in page["check_runs"]
    ]
    row["commit_statuses"] = [
        {"name": c["context"], "state": c["state"], "url": c["target_url"]}
        for page in statuses
        for c in page["statuses"]
    ]
    return row, notes


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


def _add_note(notes: list[str], note: str) -> None:
    if note not in notes:
        notes.append(note)


def _note_truncation(
    notes: dict[str, list[str]],
    kinds: tuple[str, ...],
    page_info: dict[str, Any] | None,
    source: str,
) -> None:
    if (page_info or {}).get("hasNextPage"):
        note = f"{source} truncated at GitHub page size"
        for kind in kinds:
            if note not in notes[kind]:
                notes[kind].append(note)


def _take_notes(notes: list[str], row: dict[str, Any]) -> None:
    for note in row.pop("truncation_notes", []):
        _add_note(notes, note)


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    return (row["repo"], row["number"])


def load_pr_lists(
    details: bool = False,
    watched: bool = False,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    """Load PR buckets with truncation notes scoped to each bucket."""
    watch_teams = _list_setting("pr.watch_teams")
    watch_repos = _list_setting("pr.watch_repos")
    watch_owners = _list_setting("pr.watch_owners") if watched else []
    query = build_graphql(watch_teams, watch_repos, watch_owners, details)
    try:
        data = _gh_json("api", "graphql", "-f", f"query={query}")["data"]
    except (KeyError, TypeError):
        raise click.ClickException(
            "gh returned unreadable pull request lists"
        ) from None

    viewer = data["viewer"]
    login = viewer["login"]
    notes: dict[str, list[str]] = {
        key: []
        for key in (
            ("review", "team", "mine", "watched")
            if watched
            else ("review", "team", "mine")
        )
    }
    for values, kinds in (
        (watch_teams, ("review", "team")),
        (watch_repos, ("review",)),
        (watch_owners, ("watched",)),
    ):
        if len(values) > MAX_WATCH:
            for kind in kinds:
                note = f"watch sources limited to {MAX_WATCH} entries per setting"
                if note not in notes[kind]:
                    notes[kind].append(note)

    mine_block = viewer.get("pullRequests") or {}
    _note_truncation(notes, ("mine",), mine_block.get("pageInfo"), "your pull requests")
    _note_truncation(
        notes,
        ("review", "team"),
        (data.get("reviewSearch") or {}).get("pageInfo"),
        "review request search",
    )
    mine = [pr_from_node(n, details) for n in mine_block.get("nodes") or [] if n]
    review: list[dict[str, Any]] = []
    team: list[dict[str, Any]] = []
    watched_rows: list[dict[str, Any]] = []
    review_keys: set[tuple[str, int]] = set()
    team_keys: set[tuple[str, int]] = set()
    watched_keys: set[tuple[str, int]] = set()

    def add_row(row: dict[str, Any], bucket: str) -> None:
        key = _row_key(row)
        if bucket == "review":
            if key in review_keys:
                return
            review_keys.add(key)
            team_keys.discard(key)
            team[:] = [p for p in team if _row_key(p) != key]
            review.append(row)
        elif bucket == "watched":
            if key in review_keys or key in team_keys or key in watched_keys:
                return
            watched_keys.add(key)
            watched_rows.append(row)
        else:
            if key in review_keys or key in team_keys:
                return
            team_keys.add(key)
            team.append(row)

    for node in (data.get("reviewSearch") or {}).get("nodes") or []:
        if node:
            kind = _classify_review(node, login)
            if kind:
                add_row(pr_from_node(node, details), kind)

    for i, watched_team in enumerate(watch_teams[:MAX_WATCH]):
        block = data.get(f"watchTeam{i}") or {}
        _note_truncation(
            notes,
            ("review", "team"),
            block.get("pageInfo"),
            f"watched team {watched_team}",
        )
        for node in block.get("nodes") or []:
            if node:
                kind = _classify_review(node, login)
                add_row(
                    pr_from_node(node, details),
                    "review" if kind == "review" else "team",
                )

    for source, values, bucket in (
        ("Repo", watch_repos, "review"),
        ("Owner", watch_owners, "watched"),
    ):
        for i, value in enumerate(values[:MAX_WATCH]):
            block = data.get(f"watch{source}{i}") or {}
            _note_truncation(
                notes,
                (bucket,),
                block.get("pageInfo"),
                f"watched {source.lower()} {value}",
            )
            for node in block.get("nodes") or []:
                if node:
                    row = pr_from_node(node, details)
                    if not same_login(row["author"], login):
                        add_row(row, bucket)

    lists = {"review": review, "team": team, "mine": mine, "watched": watched_rows}
    for bucket, rows in lists.items():
        source = (
            "reviewers on your pull requests"
            if bucket == "mine"
            else "reviewers on review requests"
        )
        for row in rows:
            if row.pop("review_requests_truncated", False):
                _note_truncation(notes, (bucket,), {"hasNextPage": True}, source)
            _take_notes(notes[bucket], row)
    sort_key = lambda pr: (pr["repo"], pr["number"])
    return {bucket: sorted(rows, key=sort_key) for bucket, rows in lists.items()}, notes


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


def origin_slug(dest: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    if "://" in url:
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"https", "ssh"} or parsed.query or parsed.fragment:
                return None
            host = parsed.hostname
            path = parsed.path.removeprefix("/")
        except ValueError:
            return None
    else:
        match = re.fullmatch(r"(?:[^@/\s]+@)?([^:/\s]+):([^?#\s]+)", url)
        if not match:
            return None
        host, path = match.groups()
    if host is None or host.lower() != "github.com":
        return None
    return path.lower().removesuffix(".git")


def remote_matches(dest: Path, slug: str) -> bool:
    origin = origin_slug(dest)
    if origin is None:
        return False
    if origin == slug.lower():
        return True
    result = run_gh(
        "repo",
        "view",
        f"github.com/{slug}",
        "--json",
        "nameWithOwner",
        "-q",
        ".nameWithOwner",
    )
    return result.returncode == 0 and result.stdout.strip().lower() == origin


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

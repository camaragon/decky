"""GraphQL list loading and bucketing."""

from __future__ import annotations

import json
import subprocess

import click
import pytest

from decky import github


def _node(
    repo: str,
    number: int,
    *,
    state: str | None = "SUCCESS",
    draft: bool = False,
    author: str = "dev",
    user_request: bool = True,
    team_request: bool = False,
    approvals: int = 0,
) -> dict:
    reviews = [{"state": "APPROVED"}] * approvals
    requests = []
    if user_request:
        requests.append({"requestedReviewer": {"login": "viewer"}})
    if team_request:
        requests.append({"requestedReviewer": {"slug": "eng"}})
    return {
        "number": number,
        "title": f"t{number}",
        "isDraft": draft,
        "updatedAt": "2026-01-01T00:00:00Z",
        "author": {"login": author},
        "repository": {"nameWithOwner": repo},
        "commits": {
            "nodes": [{"commit": {"statusCheckRollup": {"state": state} if state else None}}]
        },
        "latestOpinionatedReviews": {"nodes": reviews},
        "reviewRequests": {"pageInfo": {"hasNextPage": False}, "nodes": requests},
    }


def test_buckets_user_before_team(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "data": {
            "viewer": {
                "login": "viewer",
                "pullRequests": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            },
            "reviewSearch": {
                "pageInfo": {"hasNextPage": False},
                "nodes": [
                    _node("o/r", 1, user_request=True, team_request=True),
                    _node("o/r", 2, user_request=False, team_request=True),
                ],
            },
        }
    }
    monkeypatch.setattr(
        github,
        "run_gh",
        lambda *a: subprocess.CompletedProcess([], 0, stdout=json.dumps(payload)),
    )
    lists, _ = github.load_pr_lists()
    assert [p["number"] for p in lists["review"]] == [1]
    assert [p["number"] for p in lists["team"]] == [2]


def test_mine_from_viewer(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "data": {
            "viewer": {
                "login": "viewer",
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False},
                    "nodes": [_node("me/w", 3, user_request=False, team_request=False)],
                },
            },
            "reviewSearch": {"pageInfo": {"hasNextPage": False}, "nodes": []},
        }
    }
    monkeypatch.setattr(
        github,
        "run_gh",
        lambda *a: subprocess.CompletedProcess([], 0, stdout=json.dumps(payload)),
    )
    lists, _ = github.load_pr_lists()
    assert [p["number"] for p in lists["mine"]] == [3]


def _truncation_payload(mine: bool, search: bool) -> dict:
    return {
        "data": {
            "viewer": {
                "login": "v",
                "pullRequests": {"pageInfo": {"hasNextPage": mine}, "nodes": []},
            },
            "reviewSearch": {"pageInfo": {"hasNextPage": search}, "nodes": []},
        }
    }


@pytest.mark.parametrize(
    "mine,search,expected",
    [
        (True, False, {"mine": ["your pull requests truncated at GitHub page size"], "review": [], "team": []}),
        (
            False,
            True,
            {
                "mine": [],
                "review": ["review request search truncated at GitHub page size"],
                "team": ["review request search truncated at GitHub page size"],
            },
        ),
    ],
)
def test_truncation_note_scoped_to_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path, mine: bool, search: bool, expected: dict
) -> None:
    from fastapi.testclient import TestClient

    from decky.server.app import create_app

    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    payload = _truncation_payload(mine, search)
    monkeypatch.setattr(
        github,
        "run_gh",
        lambda *a: subprocess.CompletedProcess([], 0, stdout=json.dumps(payload)),
    )
    _, notes = github.load_pr_lists()
    assert notes == expected
    client = TestClient(create_app(static=None), base_url="http://127.0.0.1")
    for kind, kind_notes in expected.items():
        assert client.get(f"/api/tables/{kind}").json()["notes"] == kind_notes


def test_watch_repo_search_merged(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "data": {
            "viewer": {
                "login": "viewer",
                "pullRequests": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            },
            "reviewSearch": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "watchRepo0": {
                "pageInfo": {"hasNextPage": False},
                "nodes": [_node("acme/api", 5, author="other", user_request=False, team_request=False)],
            },
        }
    }

    def fake_run(*args: str) -> subprocess.CompletedProcess[str]:
        assert "watchRepo0" in args[-1]
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload))

    monkeypatch.setattr(github, "run_gh", fake_run)
    monkeypatch.setattr(
        github.config,
        "resolve",
        lambda key: (
            (["acme/api"], "file")
            if key == "pr.watch_repos"
            else (([], "default") if key == "pr.watch_teams" else (None, "unset"))
        ),
    )
    lists, _ = github.load_pr_lists()
    assert [p["number"] for p in lists["review"]] == [5]


def test_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = subprocess.CompletedProcess([], 1, stderr="rate limit exceeded")
    good = subprocess.CompletedProcess([], 0, stdout="ok")
    calls: list[int] = []

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(1)
        return bad if len(calls) == 1 else good

    slept: list[float] = []
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(github.time, "sleep", slept.append)
    assert github.run_gh("api", "graphql").stdout == "ok"
    assert slept == [2]

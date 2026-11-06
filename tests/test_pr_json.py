"""Versioned PR JSON through the CLI and GitHub response boundary."""

import json
import subprocess

import pytest
from click.testing import CliRunner

from decky import github, tui
from decky.cli import cli
from tests.test_github import _node


@pytest.fixture
def node():
    row = _node("example/api", 8, approvals=2)
    row.update(
        url="https://github.com/example/api/pull/8",
        body="Review this.",
        reviewDecision="APPROVED",
        labels={"nodes": [{"name": "bug"}]},
    )
    return row


@pytest.mark.parametrize(
    "flags,keys,numbers",
    [
        ([], ["review", "team", "mine", "watched"], [8]),
        (["--all"], ["review", "team", "mine", "watched"], [8, 9, 10, 11]),
        (["--mine"], ["mine"], []),
        (["--team"], ["team"], []),
    ],
)
def test_json_buckets_and_filters(monkeypatch, tmp_path, node, flags, keys, numbers):
    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("DECKY_PR_HIDE_AUTHORS", "renovate")
    rows = [
        node,
        _node("example/api", 9, draft=True),
        _node("example/api", 10, state="FAILURE"),
        _node("example/api", 11, author="renovate[bot]"),
    ]
    payload = {
        "viewer": {"login": "viewer", "pullRequests": {"nodes": []}},
        "reviewSearch": {"nodes": rows, "pageInfo": {"hasNextPage": True}},
    }
    monkeypatch.setattr(
        github,
        "run_gh",
        lambda *a: subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"data": payload})
        ),
    )
    monkeypatch.setattr(
        tui, "choose", lambda *a, **kw: pytest.fail("JSON opened picker")
    )
    result = CliRunner().invoke(cli, ["pr", "list", "--json", "-i", *flags])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["version"] == 1 and list(data["buckets"]) == keys
    assert [p["number"] for p in data["buckets"].get("review", [])] == numbers
    assert data["hidden"] == {
        key: (3 if key == "review" and not flags else 0) for key in keys
    }
    assert data["notes"] == ["list truncated at GitHub page size"]
    if numbers:
        row = data["buckets"]["review"][0]
        assert row == {
            "number": 8,
            "repo": "example/api",
            "repo_owner": "example",
            "repo_name": "api",
            "url": node["url"],
            "title": "t8",
            "author": "dev",
            "body": "Review this.",
            "draft": False,
            "checks": "pass",
            "approvals": 2,
            "review_decision": "APPROVED",
            "labels": ["bug"],
            "updated_at": "2026-01-01T00:00:00Z",
        }


def test_owner_sources_deduplicate_and_preserve_mine(monkeypatch, tmp_path, node):
    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("DECKY_PR_WATCH_OWNERS", "example,personal")
    monkeypatch.setenv("DECKY_PR_WATCH_REPOS", "example/api")
    own = _node("personal/app", 2, author="viewer")
    team_only = _node("example/api", 5, user_request=False, team_request=True)
    other = _node("example/web", 6, user_request=False)
    payload = {
        "viewer": {"login": "viewer", "pullRequests": {"nodes": [own]}},
        "reviewSearch": {"nodes": [node, team_only]},
        "watchRepo0": {"nodes": [node]},
        "watchOwner0": {"nodes": [node, team_only, other, other]},
        "watchOwner1": {"nodes": [own]},
    }

    def fetch(*args):
        assert "user:example is:pr is:open" in args[-1]
        assert "user:personal is:pr is:open" in args[-1]
        return subprocess.CompletedProcess([], 0, stdout=json.dumps({"data": payload}))

    monkeypatch.setattr(github, "run_gh", fetch)
    result = CliRunner().invoke(cli, ["pr", "list", "--json", "--all"])
    assert result.exit_code == 0, result.output
    buckets = json.loads(result.stdout)["buckets"]
    assert [p["number"] for p in buckets["review"]] == [8]
    assert [p["number"] for p in buckets["team"]] == [5]
    assert [p["number"] for p in buckets["watched"]] == [6]
    assert [p["number"] for p in buckets["mine"]] == [2]


def test_non_json_callers_skip_details(monkeypatch, tmp_path, node):
    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    payload = {
        "viewer": {"login": "viewer", "pullRequests": {"nodes": []}},
        "reviewSearch": {"nodes": [node]},
    }

    def fetch(*args):
        assert "body" not in args[-1] and "labels" not in args[-1]
        return subprocess.CompletedProcess([], 0, stdout=json.dumps({"data": payload}))

    monkeypatch.setattr(github, "run_gh", fetch)
    lists, _ = github.load_pr_lists()
    assert not {"body", "labels", "review_decision", "repo_owner"} & set(
        lists["review"][0]
    )

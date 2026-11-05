"""decky pr list."""

from __future__ import annotations

import subprocess

import pytest
from click.testing import CliRunner

from decky.cli import cli
from decky.commands import pr as pr_cmd
from decky import tui

PRS = [
    {
        "number": 7,
        "repo": "acme/api",
        "title": "Fix login",
        "checks": "pass",
        "approvals": 2,
        "draft": False,
        "author": "dev",
    },
    {
        "number": 1234,
        "repo": "acme/web-app",
        "title": "Add page",
        "checks": "fail",
        "approvals": 0,
        "draft": False,
        "author": "dev",
    },
    {
        "number": 9,
        "repo": "acme/api",
        "title": "WIP",
        "checks": "pass",
        "approvals": 0,
        "draft": True,
        "author": "dev",
    },
    {
        "number": 5,
        "repo": "acme/api",
        "title": "Bump",
        "checks": "pass",
        "approvals": 0,
        "draft": False,
        "author": "renovate",
    },
]

LISTS = {"review": PRS, "team": [], "mine": []}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_table_with_all(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.setattr(pr_cmd, "fetch_lists", lambda: (LISTS, []))
    result = runner.invoke(cli, ["pr", "ls", "--all"])
    assert result.exit_code == 0, result.output
    assert "DRAFT" in result.output.splitlines()[0]
    assert "#7" in result.output


def test_default_filter(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.setattr(pr_cmd, "fetch_lists", lambda: (LISTS, []))
    result = runner.invoke(cli, ["pr", "ls"])
    assert result.exit_code == 0
    assert "hidden (draft, not passing, or hidden author)" in result.output
    assert "#7" in result.output
    assert "#1234" not in result.output


def test_mine_and_team_error(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["pr", "ls", "-m", "-t"])
    assert result.exit_code == 2


def test_empty(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.setattr(pr_cmd, "fetch_lists", lambda: ({"review": [], "team": [], "mine": []}, []))
    result = runner.invoke(cli, ["pr", "ls"])
    assert result.output.strip() == "no review requests"


def test_interactive_open(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.setattr(pr_cmd, "fetch_lists", lambda: (LISTS, []))
    picks = [("open", 1)]
    monkeypatch.setattr(
        tui,
        "choose",
        lambda rows, index=0, hint="", actions=(): picks.pop(0),
    )
    reviews: list[tuple[str, int]] = []
    monkeypatch.setattr(pr_cmd, "open_review", lambda slug, n: reviews.append((slug, n)))
    result = runner.invoke(cli, ["pr", "ls", "-i", "--all"])
    assert result.exit_code == 0
    assert reviews == [("acme/web-app", 1234)]


def test_interactive_mine_open_review(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    lists = {"review": [], "team": [], "mine": PRS}
    monkeypatch.setattr(pr_cmd, "fetch_lists", lambda: (lists, []))
    picks = [("open", 0)]
    monkeypatch.setattr(
        tui,
        "choose",
        lambda rows, index=0, hint="", actions=(): picks.pop(0),
    )
    reviews: list[tuple[str, int]] = []
    monkeypatch.setattr(pr_cmd, "open_review", lambda slug, n: reviews.append((slug, n)))
    result = runner.invoke(cli, ["pr", "ls", "-i", "-m", "--all"])
    assert result.exit_code == 0
    assert reviews == [("acme/api", 7)]


def test_review_missing_command(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pr_cmd.config,
        "resolve",
        lambda key: (None, "unset"),
    )
    clone = []
    monkeypatch.setattr(pr_cmd.github, "clone_or_reuse", lambda *a: clone.append(1))
    result = runner.invoke(cli, ["pr", "review", "o/r", "1", "--org", "ignored"])
    assert result.exit_code == 2
    assert clone == []

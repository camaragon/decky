"""Config file and decky config subcommands."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from decky.cli import cli
from decky import config


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("DECKY_CONFIG", str(path))
    return path


def test_init_writes_placeholder_command(isolated_config: Path, runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "init"])
    assert result.exit_code == 0
    text = isolated_config.read_text(encoding="utf-8")
    assert "your-review-agent {url}" in text
    assert "your-queue-script" in text
    assert "claude" not in text.lower() or "your-review-agent" in text


def test_set_queue_command(isolated_config: Path, runner: CliRunner) -> None:
    runner.invoke(cli, ["config", "set", "queue.command", "echo-json"])
    value, source = config.resolve("queue.command")
    assert value == "echo-json"
    assert source == "file"


def test_init_refuses_existing(isolated_config: Path, runner: CliRunner) -> None:
    isolated_config.write_text("x = 1\n", encoding="utf-8")
    result = runner.invoke(cli, ["config", "init"])
    assert result.exit_code != 0


def test_get_missing_exits_1(isolated_config: Path, runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "get", "work_org"])
    assert result.exit_code == 1


def test_set_and_get(isolated_config: Path, runner: CliRunner) -> None:
    runner.invoke(cli, ["config", "set", "work_org", "my-org"])
    result = runner.invoke(cli, ["config", "get", "work_org"])
    assert result.exit_code == 0
    assert result.output.strip() == "my-org"


def test_unset(isolated_config: Path, runner: CliRunner) -> None:
    runner.invoke(cli, ["config", "init"])
    runner.invoke(cli, ["config", "unset", "interactive"])
    data = isolated_config.read_bytes()
    assert b"interactive" not in data


def test_bool_parse(isolated_config: Path, runner: CliRunner) -> None:
    runner.invoke(cli, ["config", "set", "interactive", "yes"])
    value, source = config.resolve("interactive")
    assert value is True
    assert source == "file"


def test_hide_authors_list(isolated_config: Path, runner: CliRunner) -> None:
    runner.invoke(cli, ["config", "set", "pr.hide_authors", "bot1,bot2"])
    value, _ = config.resolve("pr.hide_authors")
    assert value == ["bot1", "bot2"]


def test_watch_teams_and_repos_lists(isolated_config: Path, runner: CliRunner) -> None:
    runner.invoke(cli, ["config", "set", "pr.watch_teams", "acme/platform,acme/security"])
    runner.invoke(cli, ["config", "set", "pr.watch_repos", "acme/api,acme/web"])
    teams, _ = config.resolve("pr.watch_teams")
    repos, _ = config.resolve("pr.watch_repos")
    assert teams == ["acme/platform", "acme/security"]
    assert repos == ["acme/api", "acme/web"]


def test_decky_config_path_env(isolated_config: Path, runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "path"])
    assert result.output.strip() == str(isolated_config)


def test_file_mode_600(isolated_config: Path, runner: CliRunner) -> None:
    runner.invoke(cli, ["config", "init"])
    mode = stat.S_IMODE(isolated_config.stat().st_mode)
    assert mode == 0o600


def test_env_overrides_file(isolated_config: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.invoke(cli, ["config", "set", "work_org", "from-file"])
    monkeypatch.setenv("DECKY_WORK_ORG", "from-env")
    value, source = config.resolve("work_org")
    assert value == "from-env"
    assert source == "env:DECKY_WORK_ORG"


def test_unknown_key(isolated_config: Path, runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "get", "no.such.key"])
    assert result.exit_code != 0

"""Regressions for editable config and configured command diagnostics."""

import shlex
import sys

import click
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError

from decky import config, tmux
from decky.cli import cli
from decky.server import mcp
from decky.server.api import State
from decky.server.app import create_app


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("DECKY_CONFIG", str(path))
    for setting in config.SETTINGS.values():
        monkeypatch.delenv(setting.env, raising=False)
    return path, TestClient(create_app(static=None), base_url="http://127.0.0.1")


def test_effective_values_roundtrip(setup):
    path, client = setup
    path.write_text('interactive = true\n[server]\nport = 9000\n[pr]\nhide_authors = ["a,b", "bot"]\n')
    rows = {s["key"]: s for s in client.get("/api/config").json()["settings"]}
    for key in ("interactive", "server.port", "pr.hide_authors"):
        assert isinstance(rows[key]["value"], str)
        assert client.put(f"/api/config/{key}", json={"value": rows[key]["value"]}).status_code == 200
    assert config.resolve("pr.hide_authors")[0] == ["a,b", "bot"]
    assert client.delete("/api/config/interactive").status_code == 200
    row = next(s for s in client.get("/api/config").json()["settings"] if s["key"] == "interactive")
    assert (row["value"], row["source"]) == ("false", "default")
    assert client.put("/api/config/interactive", json={"value": row["value"]}).status_code == 200


@pytest.mark.parametrize("value", ["[broken", '["bot", 1]'])
def test_invalid_list_is_named_and_preserves_file(setup, value):
    path, client = setup
    path.write_text('work_org = "sample"\n')
    before = path.read_bytes()
    result = CliRunner().invoke(cli, ["config", "set", "pr.hide_authors", value])
    assert result.exit_code != 0 and "pr.hide_authors" in result.output
    response = client.put("/api/config/pr.hide_authors", json={"value": value})
    assert response.status_code == 422 and "pr.hide_authors" in response.json()["message"]
    with pytest.raises(ToolError, match="pr.hide_authors"):
        mcp.set_config(State(), "pr.hide_authors", value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("text,key", [
    ('interactive = "perhaps"', "interactive"),
    ('terminal = "invalid"', "terminal"),
    ('pr = "scalar"', "pr.hide_authors"),
    ('[pr]\nhide_authors = [1]', "pr.hide_authors"),
    ('[server]\nport = true', "server.port"),
])
def test_invalid_file_types_and_shapes(setup, text, key):
    path, client = setup
    path.write_text(text)
    result = CliRunner().invoke(cli, ["config", "get", key])
    assert result.exit_code != 0 and key in result.output
    response = client.get("/api/config")
    assert response.status_code == 422 and key.split(".")[0] in response.json()["message"]
    if key.startswith("pr."):
        before = path.read_bytes()
        response = client.put(f"/api/config/{key}", json={"value": "bot"})
        if text.startswith("pr ="):
            assert response.status_code == 422
            assert client.delete(f"/api/config/{key}").status_code == 422
            assert path.read_bytes() == before


def test_env_and_valid_list_formats(setup, monkeypatch):
    monkeypatch.setenv("DECKY_PR_HIDE_AUTHORS", "[broken")
    with pytest.raises(click.ClickException, match="pr.hide_authors.*DECKY_PR_HIDE_AUTHORS"):
        config.resolve("pr.hide_authors")
    for raw in ('bot, helper', '["bot", "helper"]'):
        monkeypatch.setenv("DECKY_PR_HIDE_AUTHORS", raw)
        assert config.resolve("pr.hide_authors")[0] == ["bot", "helper"]


@pytest.mark.parametrize("setting,route", [
    ("queue.command", "/api/queue"), ("status.command", "/api/status"),
    ("browser.command", "/api/open-url"),
])
@pytest.mark.parametrize("failure", ["missing", "quote", "empty", "exit", "permission"])
def test_command_errors_are_json_and_bounded(setup, setting, route, failure):
    path, client = setup
    commands = {"missing": "/definitely/missing/executable", "quote": "'broken", "empty": "   ",
                "exit": f'{shlex.quote(sys.executable)} -c "raise SystemExit(7)"', "permission": str(path)}
    config.set_value(setting, commands[failure])
    response = client.post(route, json={"url": "https://example.com"}) if route.endswith("open-url") else client.get(route)
    assert response.status_code == 422
    message = response.json()["message"]
    assert setting in message and len(message) < 300
    if failure == "exit":
        assert "7" in message


def test_review_launch_errors_reach_cli_and_mcp(setup, monkeypatch):
    config.set_value("tmux.bin", "/definitely/missing/executable")
    backend = tmux.TmuxBackend()
    monkeypatch.setattr("decky.commands.pr.open_review", lambda *_: backend.focus_existing("sample", "https://example.com"))
    result = CliRunner().invoke(cli, ["pr", "review", "sample/repo", "1"])
    assert result.exit_code != 0 and "tmux.bin" in result.output
    with pytest.raises(ToolError, match="tmux.bin"):
        mcp.start_review(State(), "sample/repo", 1)


def test_save_failure_is_actionable_and_preserves_file(setup, monkeypatch):
    path, client = setup
    path.write_text('work_org = "sample"\n')
    before = path.read_bytes()

    def fail(*_):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(config.os, "replace", fail)
    response = client.put("/api/config/work_org", json={"value": "updated"})
    assert response.status_code == 422
    assert "cannot save config file" in response.json()["message"]
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".config-*"))

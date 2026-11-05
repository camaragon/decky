"""decky server click command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from decky.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_server_uvicorn_defaults(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(app, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("decky.commands.server.uvicorn.run", fake_run)
    monkeypatch.setattr("decky.commands.server.browser.open_http_url", lambda url: None)
    result = runner.invoke(cli, ["server", "--no-open"])
    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8777


def test_invalid_port_config(runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[server]\nport = "nope"\n', encoding="utf-8")
    monkeypatch.setenv("DECKY_CONFIG", str(cfg))
    result = runner.invoke(cli, ["server", "--no-open"])
    assert result.exit_code == 2


def test_invalid_log_level(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["server", "--no-open", "--log-level", "trace"])
    assert result.exit_code == 2

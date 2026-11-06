"""decky server click command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from decky.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_server_uvicorn_defaults(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def fake_run(app, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("decky.commands.server.uvicorn.run", fake_run)
    monkeypatch.setattr("decky.commands.server.browser.open_http_url", lambda url: None)
    result = runner.invoke(cli, ["server", "--no-open"])
    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8777


def test_invalid_port_config(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[server]\nport = "nope"\n', encoding="utf-8")
    monkeypatch.setenv("DECKY_CONFIG", str(cfg))
    result = runner.invoke(cli, ["server", "--no-open"])
    assert result.exit_code == 2


def test_invalid_log_level(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["server", "--no-open", "--log-level", "trace"])
    assert result.exit_code == 2


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.1"])
def test_non_loopback_warning(runner, monkeypatch, host) -> None:
    monkeypatch.setattr("decky.commands.server.uvicorn.run", lambda *a, **kw: None)
    result = runner.invoke(cli, ["server", "--host", host, "--no-open"])
    assert result.exit_code == 0
    assert "warning:" in result.output
    assert "no authentication" in result.output


@pytest.mark.parametrize("dev", [False, True])
def test_ipv6_startup_url(runner, monkeypatch, dev) -> None:
    opened = []
    monkeypatch.setattr("decky.commands.server.uvicorn.run", lambda *a, **kw: None)
    monkeypatch.setattr("decky.commands.server.browser.open_http_url", opened.append)
    result = runner.invoke(
        cli, ["server", "--host", "::1", *(["--dev"] if dev else [])]
    )
    assert result.exit_code == 0
    if dev:
        assert "http://[::1]:8777" in result.output
    else:
        assert opened == ["http://[::1]:8777/"]

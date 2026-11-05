"""`decky server`: local web UI and JSON API."""

from __future__ import annotations

import logging

import click
import uvicorn

from decky import browser, config
from decky.server import create_app
from decky.server.app import STATIC

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
LOG_LEVELS = {"debug", "info", "warning", "error"}


def _resolve_port(port: int | None) -> int:
    if port is not None:
        return port
    raw, _ = config.resolve("server.port")
    try:
        return int(raw or 8777)
    except (TypeError, ValueError):
        raise click.UsageError(f"server.port must be an integer, not {raw!r}") from None


def _warn_non_loopback(host: str) -> None:
    if host.lower() not in LOOPBACK and host not in ("0.0.0.0", "::"):
        click.echo(
            "warning: binding to a non-loopback address; mutating API routes have no auth",
            err=True,
        )


def _open_ui(host: str, port: int, no_open: bool, dev: bool) -> None:
    if no_open or dev:
        return
    if host in ("0.0.0.0", "::"):
        url = f"http://127.0.0.1:{port}/"
    else:
        url = f"http://{host}:{port}/"
    browser.open_http_url(url)


@click.command("server")
@config.option("server.host", "--host")
@click.option("--port", type=int, default=None)
@click.option("--no-open", is_flag=True)
@click.option("--dev", is_flag=True)
@config.option("server.log_level", "--log-level")
def server_cmd(host: str, port: int | None, no_open: bool, dev: bool, log_level: str) -> None:
    """Serve the decky web UI and API."""
    port = _resolve_port(port)
    level = (log_level or "warning").lower()
    if level not in LOG_LEVELS:
        raise click.UsageError(f"--log-level must be one of {', '.join(sorted(LOG_LEVELS))}")
    _warn_non_loopback(host)
    logging.getLogger("decky").setLevel(level.upper())
    static = None if dev else STATIC
    app = create_app(host=host, static=static)
    if dev:
        click.echo(
            f"API on http://{host}:{port} (SPA via pnpm -C web dev at http://127.0.0.1:5173/)"
        )
    try:
        _open_ui(host, port, no_open, dev)
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning",
            log_config=None,
            access_log=False,
        )
    except OSError as e:
        if "address already in use" in str(e).lower():
            raise click.ClickException(f"address already in use: {host}:{port}") from e
        raise

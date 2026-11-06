"""Open http(s) URLs with browser.command."""

from __future__ import annotations

import click

from decky import config
from decky.process import launch


def open_http_url(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        raise click.ClickException("url must start with http:// or https://")
    browser_cmd, _ = config.resolve("browser.command")
    if not browser_cmd:
        raise click.ClickException("set browser.command (see decky config init)")
    interpolated = str(browser_cmd).replace("{url}", url)
    launch(interpolated, "browser.command")

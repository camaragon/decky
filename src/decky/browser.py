"""Open http(s) URLs with browser.command."""

from __future__ import annotations

import shlex
import subprocess

import click

from decky import config


def open_http_url(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        raise click.ClickException("url must start with http:// or https://")
    browser_cmd, _ = config.resolve("browser.command")
    if not browser_cmd:
        raise click.ClickException("set browser.command (see decky config init)")
    interpolated = str(browser_cmd).replace("{url}", url)
    argv = shlex.split(interpolated)
    subprocess.run(argv, shell=False, check=False)

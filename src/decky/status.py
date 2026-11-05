"""Optional waiting/running strip from status.command JSON."""

from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any

import click

from decky import config

MAX_STDOUT = 8192
MAX_ITEMS = 50
MAX_TITLE = 200
MAX_URL = 2000


def _valid_item(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    title = raw.get("title")
    url = raw.get("url")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    title = title.strip()[:MAX_TITLE]
    url = url[:MAX_URL]
    out: dict[str, str] = {"title": title, "url": url}
    subtitle = raw.get("subtitle")
    if isinstance(subtitle, str) and subtitle.strip():
        out["subtitle"] = subtitle.strip()[:MAX_TITLE]
    state = raw.get("state")
    if isinstance(state, str) and state.strip():
        out["state"] = state.strip()[:80]
    return out


def _parse_list(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        parsed = _valid_item(item)
        if parsed:
            out.append(parsed)
        if len(out) >= MAX_ITEMS:
            break
    return out


def load_status() -> dict[str, Any]:
    command, _ = config.resolve("status.command")
    if not command:
        return {"disabled": True}
    argv = shlex.split(str(command))
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
    except subprocess.TimeoutExpired as e:
        raise click.ClickException("status.command timed out after 5s") from e
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise click.ClickException(err or f"status.command exited {result.returncode}")
    stdout = result.stdout or ""
    if len(stdout.encode("utf-8")) > MAX_STDOUT:
        raise click.ClickException("status.command output exceeds 8 KiB")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"status.command did not print JSON: {e}") from e
    if not isinstance(data, dict):
        raise click.ClickException("status.command JSON must be an object")
    waiting = _parse_list(data.get("waiting"))
    running = _parse_list(data.get("running"))
    return {"disabled": False, "waiting": waiting, "running": running}

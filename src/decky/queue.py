"""Optional PR queue from queue.command JSON."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from typing import Any

import click

from decky import config

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_STDOUT = 1_048_576
GITHUB_SLUG = re.compile(r"https://github\.com/([^/]+/[^/]+)/pull/\d+", re.I)


def _int_setting(key: str, default: int) -> int:
    value, _ = config.resolve(key)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def queue_timeout() -> int:
    return _int_setting("queue.timeout", DEFAULT_TIMEOUT)


def queue_max_stdout() -> int:
    return _int_setting("queue.max_stdout", DEFAULT_MAX_STDOUT)


def repo_slug(item: dict[str, Any]) -> str:
    url = item.get("url", "")
    if isinstance(url, str):
        match = GITHUB_SLUG.match(url)
        if match:
            return match.group(1)
    repo = item.get("repo", "")
    if isinstance(repo, str) and "/" in repo:
        return repo
    org, _ = config.resolve("work_org")
    if org and isinstance(repo, str) and repo:
        return f"{org}/{repo}"
    raise click.ClickException("queue item missing a resolvable repo slug")


def _parse_jira(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(k).strip() for k in raw if isinstance(k, str) and k.strip()]


def _parse_pr(raw: Any, *, allow_reviewed: bool) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    number = raw.get("number")
    title = raw.get("title")
    url = raw.get("url")
    if not isinstance(number, int) or number < 1:
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    out: dict[str, Any] = {
        "number": number,
        "title": title.strip(),
        "url": url[:2000],
        "repo": str(raw.get("repo") or ""),
        "author": str(raw.get("author") or ""),
        "opened": str(raw.get("opened") or ""),
        "draft": bool(raw.get("draft")),
        "jira": _parse_jira(raw.get("jira")),
    }
    if allow_reviewed and isinstance(raw.get("reviewed"), bool):
        out["reviewed"] = raw["reviewed"]
    return out


def _parse_list(raw: Any, *, allow_reviewed: bool) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        parsed = _parse_pr(item, allow_reviewed=allow_reviewed)
        if parsed:
            out.append(parsed)
    return out


def load_queue() -> dict[str, Any]:
    command, _ = config.resolve("queue.command")
    if not command:
        return {"disabled": True}
    timeout = queue_timeout()
    max_stdout = queue_max_stdout()
    argv = shlex.split(str(command))
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as e:
        raise click.ClickException(f"queue.command timed out after {timeout}s") from e
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise click.ClickException(err or f"queue.command exited {result.returncode}")
    stdout = result.stdout or ""
    size = len(stdout.encode("utf-8"))
    if size > max_stdout:
        raise click.ClickException(f"queue.command output exceeds {max_stdout} bytes")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"queue.command did not print JSON: {e}") from e
    if not isinstance(data, dict):
        raise click.ClickException("queue.command JSON must be an object")
    return {
        "disabled": False,
        "today": str(data.get("today") or ""),
        "mine": _parse_list(data.get("mine"), allow_reviewed=False),
        "direct": _parse_list(data.get("direct"), allow_reviewed=True),
        "team": _parse_list(data.get("team"), allow_reviewed=True),
    }

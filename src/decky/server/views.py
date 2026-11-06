"""Shape PR rows and config for the decky server API."""

from __future__ import annotations

import json
import os
from typing import Any

import click

from decky import config, github
from decky.commands.pr import pr_url


class SettingError(Exception):
    """A setting could not be saved."""


def pr_row(pr: dict) -> dict:
    row = dict(pr)
    row["url"] = pr_url(pr["repo"], pr["number"])
    return row


def fetch_table(kind: str) -> dict:
    lists, notes = github.load_pr_lists()
    if kind not in lists:
        raise click.ClickException(f"unknown table {kind!r}")
    rows = [pr_row(p) for p in lists[kind]]
    return {"rows": rows, "notes": notes[kind]}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _raw_value(s: config.Setting) -> tuple[Any, str]:
    if os.environ.get(s.env):
        return os.environ[s.env], f"env:{s.env}"
    try:
        return config.file_value(s.key), "file"
    except click.ClickException:
        return None, "file"


def config_settings() -> list[dict]:
    """Return editable text per key; invalid keys carry their raw value and error."""
    out: list[dict] = []
    for key in sorted(config.SETTINGS):
        s = config.SETTINGS[key]
        error = None
        try:
            value, source = config.resolve(key)
        except click.ClickException as e:
            value, source = _raw_value(s)
            error = e.message
        out.append(
            {
                "key": key,
                "value": _text(value),
                "source": source,
                "help": s.help,
                "kind": s.kind,
                "error": error,
            }
        )
    return out


def save_setting(key: str, value: str, unset: bool = False) -> str:
    value = value.strip()
    try:
        if unset or not value:
            config.unset_value(key)
            return f"removed {key}"
        parsed = config.parse_set_value(key, value)
        overridden = config.set_value(key, parsed)
        msg = f"saved {key}"
        if overridden:
            msg += f"; {config.setting(key).env} is set and overrides it"
        return msg
    except click.ClickException as e:
        raise SettingError(str(e)) from e
    except click.BadParameter as e:
        raise SettingError(str(e)) from e

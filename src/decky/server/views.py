"""Shape PR rows and config for the decky server API."""

from __future__ import annotations

import json

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
    return {"rows": rows, "notes": notes}


def config_settings() -> list[dict]:
    """Return editable text: JSON lists, lowercase booleans, and scalar strings."""
    out: list[dict] = []
    for key in sorted(config.SETTINGS):
        s = config.SETTINGS[key]
        value, source = config.resolve(key)
        shown = value
        if value is None:
            shown = None
        elif isinstance(value, list):
            shown = json.dumps(value)
        elif isinstance(value, bool):
            shown = str(value).lower()
        else:
            shown = str(value)
        out.append(
            {
                "key": key,
                "value": shown,
                "source": source,
                "help": s.help,
                "kind": s.kind,
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

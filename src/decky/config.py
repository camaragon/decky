"""Settings resolved from env > config file > defaults."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import tomli_w

CONFIG_ENV = "DECKY_CONFIG"
DEFAULT_CONFIG_PATH = Path("~/.config/decky/config.toml")


@dataclass(frozen=True)
class Setting:
    key: str
    env: str
    help: str
    default: Any = None
    kind: str = "str"  # str | bool | path | list_str | choice


SETTINGS: dict[str, Setting] = {
    s.key: s
    for s in (
        Setting("work_org", "DECKY_WORK_ORG", "GitHub owner for bare repo names"),
        Setting(
            "interactive",
            "DECKY_INTERACTIVE",
            "Use -i by default when stdin and stdout are a TTY",
            "false",
            kind="bool",
        ),
        Setting("pr.dir", "DECKY_PR_DIR", "Parent directory for PR checkouts", kind="path"),
        Setting(
            "pr.hide_authors",
            "DECKY_PR_HIDE_AUTHORS",
            "Logins hidden in pr list unless --all",
            '["renovate"]',
            kind="list_str",
        ),
        Setting(
            "pr.watch_teams",
            "DECKY_PR_WATCH_TEAMS",
            "Team slugs (org/team) whose review requests appear in the team list",
            "[]",
            kind="list_str",
        ),
        Setting(
            "pr.watch_repos",
            "DECKY_PR_WATCH_REPOS",
            "Repos (owner/name) whose open PRs appear as review candidates",
            "[]",
            kind="list_str",
        ),
        Setting(
            "review.command",
            "DECKY_REVIEW_COMMAND",
            "Command template for the review pane (required for pr review)",
        ),
        Setting(
            "queue.command",
            "DECKY_QUEUE_COMMAND",
            "Argv command that prints PR queue JSON (today, mine, direct, team)",
        ),
        Setting(
            "jira.browse_url",
            "DECKY_JIRA_BROWSE_URL",
            "Optional Jira issue URL template with {key} for queue Jira links",
        ),
        Setting(
            "terminal",
            "DECKY_TERMINAL",
            "Review surface backend",
            "tmux",
            kind="choice",
        ),
        Setting("tmux.bin", "DECKY_TMUX_BIN", "Path to tmux", kind="path"),
        Setting("tmux.session", "DECKY_TMUX_SESSION", "tmux session for PR windows"),
        Setting(
            "browser.command",
            "DECKY_BROWSER_COMMAND",
            "Shell command to open the PR URL on the tmux path",
            "open {url}",
        ),
        Setting("cmux.bin", "DECKY_CMUX_BIN", "Path to cmux", kind="path"),
        Setting("cmux.group", "DECKY_CMUX_GROUP", "cmux workspace group name", "decky"),
    )
}

TERMINAL_CHOICES = ("tmux", "cmux")

BOOLEANS = {
    "true": True,
    "yes": True,
    "on": True,
    "1": True,
    "false": False,
    "no": False,
    "off": False,
    "0": False,
}


def valid_keys() -> str:
    return ", ".join(sorted(SETTINGS))


def setting(key: str) -> Setting:
    s = SETTINGS.get(key)
    if s is None:
        raise click.BadParameter(f"unknown key {key!r}; valid keys: {valid_keys()}")
    return s


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG_PATH).expanduser()


def load_file() -> dict[str, Any]:
    path = config_path()
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise click.ClickException(f"invalid config file {path}: {e}") from None


def save_file(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-")
    try:
        with os.fdopen(fd, "wb") as f:
            tomli_w.dump(data, f)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def file_value(key: str, data: dict[str, Any] | None = None) -> Any:
    node: Any = load_file() if data is None else data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _parse_env_list(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("["):
        value = json.loads(raw)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise click.ClickException(f"invalid JSON list in env value: {raw!r}")
        return value
    return [part.strip() for part in raw.split(",") if part.strip()]


def env_value(s: Setting) -> Any:
    raw = os.environ[s.env]
    if s.kind == "str" or s.kind == "path" or s.kind == "choice":
        return raw
    if s.kind == "bool":
        parsed = BOOLEANS.get(raw.lower())
        if parsed is None:
            raise click.ClickException(f"invalid boolean in {s.env}: {raw!r}")
        return parsed
    if s.kind == "list_str":
        return _parse_env_list(raw)
    return raw


def _coerce_default(s: Setting) -> Any:
    if s.default is None:
        return None
    if s.kind == "bool":
        return BOOLEANS.get(str(s.default).lower(), s.default)
    if s.kind == "list_str" and isinstance(s.default, str):
        return json.loads(s.default)
    return s.default


def resolve(key: str) -> tuple[Any, str]:
    """Return (value, source) where source is env:VAR, file, default, or unset."""
    s = setting(key)
    if os.environ.get(s.env):
        return env_value(s), f"env:{s.env}"
    value = file_value(s.key)
    if value is not None:
        return value, "file"
    default = _coerce_default(s)
    if default is not None:
        return default, "default"
    return None, "unset"


def parse_set_value(key: str, raw: str) -> Any:
    s = setting(key)
    if s.kind == "bool":
        parsed = BOOLEANS.get(raw.lower())
        if parsed is None:
            raise click.BadParameter(f"{key} must be true or false, not {raw!r}")
        return parsed
    if s.kind == "list_str":
        return _parse_env_list(raw)
    if s.kind == "choice":
        if raw not in TERMINAL_CHOICES:
            raise click.BadParameter(f"{key} must be one of {', '.join(TERMINAL_CHOICES)}")
        return raw
    return raw


def set_value(key: str, value: Any) -> bool:
    """Write KEY to the config file; return True if env overrides it."""
    s = setting(key)
    data = load_file()
    *tables, name = key.split(".")
    node = data
    for table in tables:
        node = node.setdefault(table, {})
    node[name] = value
    save_file(data)
    return bool(os.environ.get(s.env))


def unset_value(key: str) -> None:
    setting(key)
    data = load_file()
    *tables, name = key.split(".")
    parents = [data]
    for table in tables:
        child = parents[-1].get(table)
        if not isinstance(child, dict):
            return
        parents.append(child)
    parents[-1].pop(name, None)
    for table, parent in zip(reversed(tables), reversed(parents[:-1])):
        if parent.get(table):
            break
        parent.pop(table, None)
    save_file(data)


INIT_TEMPLATE = """\
# Copy to ~/.config/decky/config.toml and edit.
# work_org = "your-github-user-or-org"
interactive = true
terminal = "tmux"

[pr]
dir = "~/prs"
# Extra review sources when GitHub team membership does not cover you:
# watch_teams = ["acme-corp/platform", "acme-corp/security"]
# watch_repos = ["acme-corp/api", "acme-corp/web"]

[review]
# Required before `decky pr review` or Enter in the list.
# Placeholders: {slug} {owner} {repo} {number} {url} {cwd}
command = "your-review-agent {url}"

# [queue]
# command = "your-queue-script"

# [jira]
# browse_url = "https://tracker.example/browse/{key}"

[browser]
command = "open -a Dia {url}"
# command = "open {url}"

# [tmux]
# session = "decky"

# [cmux]
# bin = "/Applications/cmux.app/Contents/Resources/bin/cmux"
# group = "decky"
# Then set terminal = "cmux"
"""


class SettingOption(click.Option):
    def __init__(self, *args: Any, setting_key: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setting_key = setting_key

    def get_default(self, ctx: click.Context, call: bool = True) -> Any:
        value = file_value(self.setting_key)
        if value is not None:
            return value
        return super().get_default(ctx, call=call)


def option(key: str, *param_decls: str, help: str = "", **kwargs: Any):
    s = SETTINGS[key]
    if s.default is not None:
        kwargs.setdefault("default", _coerce_default(s))
    suffix = f"[config: {key}]"
    return click.option(
        *param_decls,
        cls=SettingOption,
        setting_key=key,
        envvar=s.env,
        show_envvar=True,
        help=f"{help or s.help}  {suffix}",
        **kwargs,
    )


def interactive_option(help: str):
    return click.option(
        "-i/-I",
        "--interactive/--no-interactive",
        default=None,
        help=f"{help}  [config: interactive]",
    )


def in_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def interactive(flag: bool | None) -> bool:
    if flag is not None:
        return flag
    value, source = resolve("interactive")
    on = BOOLEANS.get(str(value).lower())
    if on is None:
        raise click.ClickException(f"interactive ({source}) must be true or false, not {value!r}")
    return on and in_terminal()

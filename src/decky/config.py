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
    kind: str = "str"  # str | bool | path | list_str | choice | int
    choices: tuple[str, ...] | None = None


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
        Setting(
            "pr.dir", "DECKY_PR_DIR", "Parent directory for PR checkouts", kind="path"
        ),
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
            "pr.watch_owners",
            "DECKY_PR_WATCH_OWNERS",
            "Owners (users or organizations) whose open PRs fill the JSON watched bucket",
            "[]",
            kind="list_str",
        ),
        Setting("review.owners", "DECKY_REVIEW_OWNERS", "Owners for the authored review inbox", "[]", kind="list_str"),
        Setting("review.all_owners", "DECKY_REVIEW_ALL_OWNERS", "Include authored open PRs across all owners", "false", kind="bool"),
        Setting("review.exclude_owners", "DECKY_REVIEW_EXCLUDE_OWNERS", "Owners excluded when review.all_owners is enabled", "[]", kind="list_str"),
        Setting("review.decision_command", "DECKY_REVIEW_DECISION_COMMAND", "Argv receiving review answers as JSON on stdin", "[]", kind="list_str"),
        Setting("review.results_dir", "DECKY_REVIEW_RESULTS_DIR", "Local review-result directory (unset disables results)", kind="path"),
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
            "queue.timeout",
            "DECKY_QUEUE_TIMEOUT",
            "Seconds to wait for queue.command stdout",
            "30",
            kind="int",
        ),
        Setting(
            "queue.max_stdout",
            "DECKY_QUEUE_MAX_STDOUT",
            "Maximum queue.command stdout size in bytes",
            "1048576",
            kind="int",
        ),
        Setting(
            "jira.browse_url",
            "DECKY_JIRA_BROWSE_URL",
            "Optional Jira issue URL template with {key} for queue Jira links",
        ),
        Setting(
            "status.command",
            "DECKY_STATUS_COMMAND",
            "Argv command that prints waiting/running JSON (optional)",
        ),
        Setting("server.allowed_hosts", "DECKY_SERVER_ALLOWED_HOSTS", "Extra exact hostnames accepted behind an authenticated proxy", "[]", kind="list_str"),
        Setting(
            "server.host",
            "DECKY_SERVER_HOST",
            "Address decky server binds to",
            "127.0.0.1",
        ),
        Setting(
            "server.port",
            "DECKY_SERVER_PORT",
            "Port decky server listens on",
            "8777",
            kind="int",
        ),
        Setting(
            "server.log_level",
            "DECKY_SERVER_LOG_LEVEL",
            "Log level for decky loggers",
            "warning",
            kind="choice",
            choices=("debug", "info", "warning", "error"),
        ),
        Setting(
            "terminal",
            "DECKY_TERMINAL",
            "Review surface backend",
            "tmux",
            kind="choice",
            choices=("tmux", "cmux"),
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
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise click.ClickException(f"invalid config file {path}: {e}") from None


def save_file(data: dict[str, Any]) -> None:
    path = config_path()
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-")
    except OSError as e:
        raise click.ClickException(f"cannot save config file {path}: {e.strerror}") from None
    try:
        with os.fdopen(fd, "wb") as f:
            tomli_w.dump(data, f)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except OSError as e:
        raise click.ClickException(f"cannot save config file {path}: {e.strerror}") from None
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def file_value(key: str, data: dict[str, Any] | None = None) -> Any:
    node: Any = load_file() if data is None else data
    for part in key.split("."):
        if not isinstance(node, dict):
            raise click.ClickException(f"{key}: {part!r} requires a config table")
        if part not in node:
            return None
        node = node[part]
    return node


def validate_value(s: Setting, value: Any, source: str) -> Any:
    def invalid(expected: str) -> None:
        raise click.ClickException(f"{s.key} ({source}) must be {expected}")

    if s.kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in BOOLEANS:
            return BOOLEANS[value.lower()]
        invalid("true or false")
    if s.kind == "int":
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            invalid("a positive integer")
        try:
            number = int(value)
        except ValueError:
            invalid("a positive integer")
        if number <= 0:
            invalid("a positive integer")
        return number
    if s.kind == "list_str":
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    invalid("a valid JSON string list or comma-separated strings")
            else:
                value = [part.strip() for part in raw.split(",") if part.strip()]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            invalid("a list of strings")
        return value
    if not isinstance(value, str):
        invalid("a string")
    if s.kind == "choice" and value not in (s.choices or TERMINAL_CHOICES):
        invalid(f"one of {', '.join(s.choices or TERMINAL_CHOICES)}")
    return value


def env_value(s: Setting) -> Any:
    return validate_value(s, os.environ[s.env], s.env)


def _coerce_default(s: Setting) -> Any:
    if s.default is None:
        return None
    return validate_value(s, s.default, "default")


def resolve(key: str) -> tuple[Any, str]:
    """Return (value, source) where source is env:VAR, file, default, or unset."""
    s = setting(key)
    if os.environ.get(s.env):
        return env_value(s), f"env:{s.env}"
    value = file_value(s.key)
    if value is not None:
        return validate_value(s, value, "file"), "file"
    default = _coerce_default(s)
    if default is not None:
        return default, "default"
    return None, "unset"


def parse_set_value(key: str, raw: str) -> Any:
    return validate_value(setting(key), raw, "input")


def set_value(key: str, value: Any) -> bool:
    """Write KEY to the config file; return True if env overrides it."""
    s = setting(key)
    value = validate_value(s, value, "input")
    data = load_file()
    *tables, name = key.split(".")
    node = data
    for table in tables:
        child = node.setdefault(table, {})
        if not isinstance(child, dict):
            raise click.ClickException(f"{key}: {table!r} must be a config table")
        node = child
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
        if child is None:
            return
        if not isinstance(child, dict):
            raise click.ClickException(f"{key}: {table!r} must be a config table")
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
# watch_owners = ["example-org", "example-user"]

[review]
# With all_owners false, query only these owners; empty means no GitHub queries.
# owners = ["example-org", "example-user"]
# all_owners = false
# When all_owners is true, exclude these owners before fetching PR details.
# exclude_owners = ["example-org"]
# decision_command = ["/path/to/decision-hook", "--stdin"]
# Optional local review results; unset disables reading them.
# results_dir = "~/.local/share/decky/review-results"
# Required before `decky pr review` or Enter in the list.
# Placeholders: {slug} {owner} {repo} {number} {url} {cwd}
command = "your-review-agent {url}"

# [queue]
# command = "your-queue-script"
# timeout = "30"
# max_stdout = "1048576"

# [jira]
# browse_url = "https://tracker.example/browse/{key}"

[browser]
command = "open -a Dia {url}"
# command = "open {url}"

# [status]
# command = "your-status-command"

# [server]
# host = "127.0.0.1"
# allowed_hosts = ["review.example.com"]
# port = "8777"
# log_level = "warning"

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
            return validate_value(setting(self.setting_key), value, "file")
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
        raise click.ClickException(
            f"interactive ({source}) must be true or false, not {value!r}"
        )
    return on and in_terminal()

"""cmux workspace backend for PR review."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from shutil import which

import click

from decky import config
from decky.process import run_command

CMUX_APP_BIN = "/Applications/cmux.app/Contents/Resources/bin/cmux"


def find_cmux() -> str:
    override, _ = config.resolve("cmux.bin")
    if override:
        return str(override)
    found = which("cmux")
    if found:
        return found
    if os.access(CMUX_APP_BIN, os.X_OK):
        return CMUX_APP_BIN
    raise click.ClickException("cmux not found")


def open_cmux_app() -> None:
    run_command(["open", "-a", "cmux"], "open -a cmux", check=True)


def cmux_ready(cmux: str) -> bool:
    return (
        run_command([cmux, "ping"], "cmux.bin", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        == 0
    )


def ensure_cmux_running(cmux: str) -> None:
    if cmux_ready(cmux):
        return
    open_cmux_app()
    for _ in range(10):
        if cmux_ready(cmux):
            return
        time.sleep(0.5)
    hint = "; check `cmux socket-status` if cmux is already running"
    raise click.ClickException(f"cmux did not become ready{hint}")


def list_windows(cmux: str) -> list[dict]:
    result = run_command([cmux, "list-windows", "--json"], "cmux.bin", capture_output=True, text=True)
    if result.returncode != 0:
        raise click.ClickException("could not list cmux windows")
    try:
        windows = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise click.ClickException("cmux returned unreadable windows") from None
    if not isinstance(windows, list):
        raise click.ClickException("cmux returned unreadable windows")
    return windows


def list_workspaces(cmux: str, window: str) -> list[dict]:
    result = run_command(
        [cmux, "workspace", "list", "--window", window, "--json"], "cmux.bin",
        capture_output=True,
        text=True,
        env={**os.environ, "CMUX_QUIET": "1"},
    )
    if result.returncode != 0:
        raise click.ClickException(f"cmux.bin: command exited {result.returncode}; could not list workspaces")
    try:
        workspaces = json.loads(result.stdout)["workspaces"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    return workspaces if isinstance(workspaces, list) else []


def find_workspace(cmux: str, title: str) -> tuple[str, str] | None:
    for window in list_windows(cmux):
        for workspace in list_workspaces(cmux, window["id"]):
            if workspace.get("title") == title and workspace.get("id"):
                return window["id"], workspace["id"]
    return None


def show_workspace(cmux: str, window: str, workspace: str) -> None:
    for args in (
        ["focus-window", "--window", window],
        ["workspace", "select", "--workspace", workspace, "--window", window],
    ):
        result = run_command([cmux, *args], "cmux.bin", capture_output=True, text=True)
        if result.returncode != 0:
            raise click.ClickException(f"could not switch to cmux workspace {workspace}")
    if not os.environ.get("CMUX_WORKSPACE_ID"):
        open_cmux_app()


def find_group(cmux: str, name: str) -> str | None:
    result = run_command(
        [cmux, "workspace-group", "list", "--json"], "cmux.bin", capture_output=True, text=True
    )
    if result.returncode != 0:
        raise click.ClickException("could not list cmux workspace groups")
    try:
        groups = json.loads(result.stdout)["groups"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise click.ClickException("cmux returned unreadable workspace groups") from None
    for group in groups:
        if not isinstance(group, dict):
            continue
        if group.get("name") == name:
            ref = group.get("ref")
            if ref:
                return ref
    return None


def create_group(cmux: str, name: str, workspace_ref: str) -> None:
    result = run_command(
        [
            cmux,
            "workspace-group",
            "create",
            "--name",
            name,
            "--from",
            workspace_ref,
            "--idempotency-key",
            name,
        ],
        "cmux.bin",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise click.ClickException(f"could not create cmux workspace group {name}")


def workspace_ref(output: str) -> str | None:
    match = re.search(r"workspace:\d+", output)
    return match.group(0) if match else None


def review_layout(dest: Path, command: str, url: str) -> dict:
    return {
        "direction": "horizontal",
        "split": 0.5,
        "children": [
            {
                "pane": {
                    "surfaces": [
                        {
                            "type": "terminal",
                            "name": "review",
                            "cwd": str(dest),
                            "command": command,
                            "focus": True,
                        }
                    ]
                }
            },
            {"pane": {"surfaces": [{"type": "browser", "name": "pr", "url": url}]}},
        ],
    }


class CmuxBackend:
    def focus_existing(self, name: str, url: str) -> bool:
        cmux = find_cmux()
        ensure_cmux_running(cmux)
        found = find_workspace(cmux, name)
        if found is None:
            return False
        show_workspace(cmux, *found)
        return True

    def open(self, name: str, cwd: Path, command: str, url: str) -> None:
        cmux = find_cmux()
        ensure_cmux_running(cmux)
        group_name, _ = config.resolve("cmux.group")
        group_name = group_name or "decky"
        layout = json.dumps(review_layout(cwd, command, url))
        args = [
            "--name",
            name,
            "--cwd",
            str(cwd),
            "--focus",
            "true",
            "--layout",
            layout,
        ]
        group_ref = find_group(cmux, group_name)
        if group_ref:
            args += ["--group", group_ref]
        created = run_command(
            [cmux, "workspace", "create", *args], "cmux.bin", capture_output=True, text=True
        )
        if created.returncode != 0:
            raise click.ClickException(f"cmux.bin: command exited {created.returncode}")
        sys.stdout.write(created.stdout)
        sys.stderr.write(created.stderr)
        if group_ref:
            return
        ref = workspace_ref(created.stdout)
        if ref is None:
            click.echo(f"warning: could not find new workspace; not creating group {group_name}", err=True)
            return
        create_group(cmux, group_name, ref)

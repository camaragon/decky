"""tmux backend argv."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from decky import tmux as tmux_mod


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> tmux_mod.TmuxBackend:
    monkeypatch.setattr(tmux_mod.config, "resolve", lambda key: (None, "unset"))
    monkeypatch.setattr(tmux_mod, "which", lambda name: "/usr/bin/tmux")
    monkeypatch.setattr(tmux_mod.os, "environ", {}, raising=False)
    return tmux_mod.TmuxBackend()


def test_focus_selects_and_opens_browser(backend: tmux_mod.TmuxBackend, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if len(cmd) >= 3 and cmd[1:3] == ["list-windows", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="pr-api-1\nother\n")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        tmux_mod.review,
        "interpolate",
        lambda template, **kw: "open https://github.com/o/api/pull/1",
    )
    assert backend.focus_existing("pr-api-1", "https://github.com/o/api/pull/1")
    assert any(c[1:4] == ["select-window", "-t", "decky:pr-api-1"] for c in calls if c[0].endswith("tmux"))


def test_open_new_window(backend: tmux_mod.TmuxBackend, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if len(cmd) >= 3 and cmd[1:3] == ["has-session", "-t"]:
            return subprocess.CompletedProcess(cmd, 1)
        if len(cmd) >= 3 and cmd[1:3] == ["list-windows", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        tmux_mod.review,
        "interpolate",
        lambda template, **kw: "open https://example.com",
    )
    backend.open("pr-api-2", Path("/prs/api"), "agent", "https://github.com/o/api/pull/2")
    joined = [" ".join(c) for c in calls]
    assert any("new-session" in j and "-d" in j for j in joined)
    assert any("new-window" in j and "pr-api-2" in j for j in joined)

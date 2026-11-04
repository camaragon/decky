"""Review surface backends (tmux or cmux)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import click

from decky import cmux as cmux_mod
from decky import tmux as tmux_mod


class TerminalBackend(Protocol):
    def focus_existing(self, name: str, url: str) -> bool: ...

    def open(self, name: str, cwd: Path, command: str, url: str) -> None: ...


def get_backend(name: str) -> TerminalBackend:
    if name == "tmux":
        return tmux_mod.TmuxBackend()
    if name == "cmux":
        return cmux_mod.CmuxBackend()
    raise click.UsageError(f"unknown terminal backend {name!r}; use tmux or cmux")

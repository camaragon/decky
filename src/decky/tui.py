"""Raw TTY list picker."""

from __future__ import annotations

import shutil
import sys
import termios
import tty
from collections.abc import Callable, Sequence

import click

Action = str
KeyHandler = Callable[[int, int, str], tuple[int, Action]]


def read_key() -> str:
    ch = sys.stdin.read(1)
    if ch != "\x1b":
        return ch
    import select

    ready, _, _ = select.select([sys.stdin], [], [], 0.05)
    if not ready:
        return "esc"
    rest = sys.stdin.read(1)
    if rest not in ("[", "O"):
        return "esc"
    arrow = sys.stdin.read(1)
    if arrow in ("A", "B"):
        return "up" if arrow == "A" else "down"
    return "esc"


def selection_action(index: int, count: int, key: str) -> tuple[int, Action]:
    if key in ("\r", "\n"):
        return index, "open"
    if key in ("o", "O"):
        return index, "browse"
    if key == "\t":
        return index, "cycle"
    if key in ("a", "A"):
        return index, "all"
    if key in ("q", "Q", "esc"):
        return index, "quit"
    if key == "\x03":
        return index, "abort"
    if key in ("j", "J", "down"):
        return (index + 1) % count, "stay"
    if key in ("k", "K", "up"):
        return (index - 1) % count, "stay"
    return index, "stay"


def paint_list(rows: Sequence[str], index: int, hint: str, *, redraw: bool) -> None:
    if redraw:
        sys.stdout.write(f"\x1b[{len(rows) + 1}A")
    width = max(shutil.get_terminal_size().columns - 3, 10)
    for i, row in enumerate(rows):
        prefix = ">" if i == index else " "
        text = row if len(row) <= width else row[: width - 1] + "…"
        sys.stdout.write(f"{prefix} {text}\n")
    sys.stdout.write(f"{hint}\n")
    sys.stdout.flush()


def choose(
    rows: Sequence[str],
    index: int,
    *,
    hint: str = "",
    actions: Sequence[Action] = ("open", "browse"),
    on_key: KeyHandler | None = None,
) -> tuple[Action, int] | None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise click.ClickException("choosing from a list needs a terminal")
    if not rows:
        raise click.ClickException("empty list")
    handler = on_key or selection_action
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    painted = False
    sys.stdout.write("\x1b[?25l")
    sys.stdout.flush()
    try:
        while True:
            tty.setraw(fd)
            paint_list(rows, index, hint, redraw=painted)
            painted = True
            key = read_key()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            index, action = handler(index, len(rows), key)
            if action == "quit":
                return None
            if action == "abort":
                raise click.Abort()
            if action in actions:
                return action, index
    finally:
        sys.stdout.write("\x1b[?25h")
        if painted:
            sys.stdout.write(f"\x1b[{len(rows) + 1}A\x1b[J")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

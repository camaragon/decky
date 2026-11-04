"""TTY picker key handling."""

from __future__ import annotations

import pytest

from decky import tui


@pytest.mark.parametrize(
    ("key", "action"),
    [
        ("\n", "open"),
        ("o", "browse"),
        ("\t", "cycle"),
        ("a", "all"),
        ("q", "quit"),
        ("j", "stay"),
        ("k", "stay"),
        ("m", "stay"),
    ],
)
def test_selection_action(key: str, action: str) -> None:
    _, result = tui.selection_action(0, 3, key)
    assert result == action


def test_selection_action_wrap() -> None:
    index, action = tui.selection_action(2, 3, "j")
    assert index == 0 and action == "stay"

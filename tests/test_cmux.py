"""cmux layout and focus."""

from __future__ import annotations

import json
import subprocess

import pytest

from decky import cmux


def test_review_layout_shape() -> None:
    layout = cmux.review_layout(
        __import__("pathlib").Path("/d"),
        "cmd",
        "https://github.com/o/r/pull/1",
    )
    assert layout["direction"] == "horizontal"
    assert layout["children"][1]["pane"]["surfaces"][0]["type"] == "browser"


def test_find_group(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"groups": [{"name": "decky", "ref": "group:1"}]})
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout=payload),
    )
    assert cmux.find_group("/bin/cmux", "decky") == "group:1"

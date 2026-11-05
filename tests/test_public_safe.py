"""Ensure the public tree contains no workplace-specific literals."""

from __future__ import annotations

from pathlib import Path

# These substrings must not appear outside this file (and .git).
FORBIDDEN = (
    "adcellerant",
    "BE_CONFIG",
    "BE_PR_AGENT",
    "PRS_DIR",
    "beverts312",
    "firstmate",
    "fm-spawn",
    "fm-inbox",
    "FM_HOME",
)


def test_tree_is_public_safe() -> None:
    root = Path(__file__).resolve().parents[1]
    this = Path(__file__).resolve()
    skip_dirs = {
        ".git",
        ".venv",
        "dist",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "web/dist",
        "src/decky/server/static",
    }
    for path in root.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.is_dir():
            continue
        if path.resolve() == this:
            continue
        if path.suffix in {".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for needle in FORBIDDEN:
            assert needle not in text, f"{needle!r} found in {path.relative_to(root)}"

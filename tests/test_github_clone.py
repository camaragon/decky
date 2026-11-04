"""clone_or_reuse and remote_matches."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
import pytest

from decky import github


def test_remote_matches_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    dest = Path("/tmp/x")
    result = subprocess.CompletedProcess([], 0, stdout="git@github.com:Org/Repo.git\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: result)
    assert github.remote_matches(dest, "org/repo")


def test_clone_or_reuse_existing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dest = tmp_path / "api"
    dest.mkdir()
    monkeypatch.setattr(github, "remote_matches", lambda d, s: True)
    clone_called = []
    monkeypatch.setattr(github, "clone", lambda s, d: clone_called.append(1) or 0)
    github.clone_or_reuse("o/api", dest)
    assert clone_called == []


def test_clone_or_reuse_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dest = tmp_path / "api"
    dest.mkdir()
    monkeypatch.setattr(github, "remote_matches", lambda d, s: False)
    with pytest.raises(click.ClickException, match="exists and is not"):
        github.clone_or_reuse("o/api", dest)

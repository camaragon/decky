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


@pytest.mark.parametrize(
    "origin, matches",
    [
        ("https://github.com/Org/Repo.git", True),
        ("ssh://git@github.com/Org/Repo.git", True),
        ("git@GITHUB.COM:Org/Repo", True),
        ("https://github.com/org/repo", True),
        ("git@other.example:org/repo.git", False),
        ("https://other.example/org/repo.git", False),
        ("ssh://git@other.example/org/repo.git", False),
        ("https://github.com/prefix/org/repo.git", False),
        ("git@github.com:prefix/org/repo.git", False),
        ("https://github.com/other/repo.git", False),
        ("git@github.com:org/other.git", False),
        ("https://github.com.evil.example/org/repo.git", False),
        ("https://github.com@other.example/org/repo.git", False),
        ("https://github.com/org/repo.git?other", False),
        ("file:///org/repo", False),
        ("/org/repo", False),
        ("https://[broken/org/repo", False),
    ],
)
def test_checkout_origin_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, origin: str, matches: bool
) -> None:
    dest = tmp_path / "repo"
    dest.mkdir()
    marker = dest / "keep"
    marker.write_text("unchanged")
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=origin + "\n")

    monkeypatch.setattr(subprocess, "run", run)
    if matches:
        github.clone_or_reuse("org/repo", dest)
    else:
        with pytest.raises(click.ClickException, match="exists and is not"):
            github.clone_or_reuse("org/repo", dest)
    assert calls == [["git", "-C", str(dest), "remote", "get-url", "origin"]]
    assert marker.read_text() == "unchanged"


def test_first_checkout_uses_configured_protocol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "repo"
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        # A host-qualified, scheme-free name lets gh select HTTPS or SSH.
        assert cmd == [
            "gh",
            "repo",
            "clone",
            "github.com/org/repo",
            str(dest),
            "--",
            "--recurse-submodules",
        ]
        assert not {"capture_output", "stdout", "stderr"} & kwargs.keys()
        (dest / ".git").mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", run)
    github.clone_or_reuse("org/repo", dest)
    assert len(calls) == 1
    assert (dest / ".git").is_dir()


def test_clone_failure_is_actionable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 128)
    )
    with pytest.raises(
        click.ClickException, match=r"clone org/repo \(exit 128\).*gh auth"
    ):
        github.clone_or_reuse("org/repo", tmp_path / "repo")


def test_clone_reports_missing_gh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def run(*a, **k):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(click.ClickException, match="gh not found"):
        github.clone_or_reuse("org/repo", tmp_path / "repo")


def test_clone_or_reuse_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "api"
    dest.mkdir()
    monkeypatch.setattr(github, "remote_matches", lambda d, s: True)
    clone_called = []
    monkeypatch.setattr(github, "clone", lambda s, d: clone_called.append(1) or 0)
    github.clone_or_reuse("o/api", dest)
    assert clone_called == []


def test_clone_or_reuse_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "api"
    dest.mkdir()
    monkeypatch.setattr(github, "remote_matches", lambda d, s: False)
    with pytest.raises(click.ClickException, match="exists and is not"):
        github.clone_or_reuse("o/api", dest)

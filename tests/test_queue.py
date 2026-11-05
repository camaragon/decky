"""load_queue from queue.command."""

from __future__ import annotations

import json
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from decky import queue as queue_mod


def test_unset_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(queue_mod.config, "resolve", lambda key: (None, "unset"))
    assert queue_mod.load_queue() == {"disabled": True}


def test_valid_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        queue_mod.config,
        "resolve",
        lambda key: ("cmd", "file") if key == "queue.command" else (None, "unset"),
    )
    payload = {
        "today": "2026-11-05",
        "mine": [
            {
                "repo": "api",
                "number": 1,
                "title": "Mine",
                "author": "dev",
                "opened": "2026-11-05",
                "draft": False,
                "url": "https://github.com/acme/api/pull/1",
                "jira": ["PROJ-1"],
            }
        ],
        "direct": [
            {
                "repo": "web",
                "number": 2,
                "title": "Review me",
                "author": "peer",
                "opened": "2026-11-04",
                "draft": False,
                "url": "https://github.com/acme/web/pull/2",
                "jira": [],
                "reviewed": False,
            }
        ],
        "team": [],
    }
    monkeypatch.setattr(
        queue_mod.subprocess,
        "run",
        lambda *a, **k: CompletedProcess(args=a[0], returncode=0, stdout=json.dumps(payload), stderr=""),
    )
    out = queue_mod.load_queue()
    assert out["disabled"] is False
    assert out["today"] == "2026-11-05"
    assert out["mine"][0]["jira"] == ["PROJ-1"]
    assert out["direct"][0]["reviewed"] is False


def test_repo_slug_from_url() -> None:
    slug = queue_mod.repo_slug({"url": "https://github.com/acme/api/pull/9", "repo": "api"})
    assert slug == "acme/api"


def test_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        queue_mod.config,
        "resolve",
        lambda key: ("cmd", "file") if key == "queue.command" else (None, "unset"),
    )

    def boom(*a, **k):
        raise TimeoutExpired(cmd="cmd", timeout=5)

    monkeypatch.setattr(queue_mod.subprocess, "run", boom)
    with pytest.raises(Exception) as exc:
        queue_mod.load_queue()
    assert "timed out" in str(exc.value)

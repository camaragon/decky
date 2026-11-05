"""load_status from status.command."""

from __future__ import annotations

import json
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from decky import status as status_mod


def test_unset_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(status_mod.config, "resolve", lambda key: (None, "unset"))
    assert status_mod.load_status() == {"disabled": True}


def test_valid_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        status_mod.config,
        "resolve",
        lambda key: ("echo-json", "file") if key == "status.command" else (None, "unset"),
    )
    payload = {"waiting": [{"title": "Wait", "url": "http://127.0.0.1/x"}], "running": []}
    monkeypatch.setattr(
        status_mod.subprocess,
        "run",
        lambda *a, **k: CompletedProcess(args=a[0], returncode=0, stdout=json.dumps(payload), stderr=""),
    )
    out = status_mod.load_status()
    assert out["disabled"] is False
    assert out["waiting"] == [{"title": "Wait", "url": "http://127.0.0.1/x"}]


def test_drops_bad_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        status_mod.config,
        "resolve",
        lambda key: ("cmd", "file") if key == "status.command" else (None, "unset"),
    )
    payload = {"waiting": [{"title": "x", "url": "javascript:alert(1)"}], "running": []}
    monkeypatch.setattr(
        status_mod.subprocess,
        "run",
        lambda *a, **k: CompletedProcess(args=a[0], returncode=0, stdout=json.dumps(payload), stderr=""),
    )
    assert status_mod.load_status()["waiting"] == []


def test_oversize_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        status_mod.config,
        "resolve",
        lambda key: ("cmd", "file") if key == "status.command" else (None, "unset"),
    )
    big = "x" * 9000
    monkeypatch.setattr(
        status_mod.subprocess,
        "run",
        lambda *a, **k: CompletedProcess(args=a[0], returncode=0, stdout=big, stderr=""),
    )
    with pytest.raises(Exception) as exc:
        status_mod.load_status()
    assert "8 KiB" in str(exc.value)


def test_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        status_mod.config,
        "resolve",
        lambda key: ("cmd", "file") if key == "status.command" else (None, "unset"),
    )

    def boom(*a, **k):
        raise TimeoutExpired(cmd="cmd", timeout=5)

    monkeypatch.setattr(status_mod.subprocess, "run", boom)
    with pytest.raises(Exception) as exc:
        status_mod.load_status()
    assert "timed out" in str(exc.value)


def test_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        status_mod.config,
        "resolve",
        lambda key: ("cmd", "file") if key == "status.command" else (None, "unset"),
    )
    monkeypatch.setattr(
        status_mod.subprocess,
        "run",
        lambda *a, **k: CompletedProcess(args=a[0], returncode=1, stdout="", stderr="fail"),
    )
    with pytest.raises(Exception):
        status_mod.load_status()


def test_status_subtitle_and_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        status_mod.config,
        "resolve",
        lambda key: ("cmd", "file") if key == "status.command" else (None, "unset"),
    )
    payload = {
        "waiting": [
            {
                "title": "Task",
                "url": "http://127.0.0.1/x",
                "subtitle": "details",
                "state": "working",
            }
        ],
        "running": [],
    }
    monkeypatch.setattr(
        status_mod.subprocess,
        "run",
        lambda *a, **k: CompletedProcess(args=a[0], returncode=0, stdout=json.dumps(payload), stderr=""),
    )
    item = status_mod.load_status()["waiting"][0]
    assert item["subtitle"] == "details"
    assert item["state"] == "working"


def test_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        status_mod.config,
        "resolve",
        lambda key: ("cmd", "file") if key == "status.command" else (None, "unset"),
    )
    monkeypatch.setattr(
        status_mod.subprocess,
        "run",
        lambda *a, **k: CompletedProcess(args=a[0], returncode=0, stdout="not-json", stderr=""),
    )
    with pytest.raises(Exception):
        status_mod.load_status()

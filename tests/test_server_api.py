"""decky server HTTP API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from decky.commands import pr as pr_cmd
from decky.server.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    empty_static = tmp_path / "static"
    empty_static.mkdir()
    return TestClient(create_app(host="127.0.0.1", static=empty_static), base_url="http://127.0.0.1")


def test_meta(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pr_cmd.config,
        "resolve",
        lambda key: ("x", "file") if key == "review.command" else (None, "unset"),
    )
    res = client.get("/api/meta")
    assert res.status_code == 200
    assert res.json()["reviewConfigured"] is True


def test_status_disabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "decky.server.api.load_status",
        lambda: {"disabled": True},
    )
    assert client.get("/api/status").json() == {"disabled": True}


def test_table_review(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    row = {
        "number": 1,
        "repo": "o/r",
        "author": "a",
        "checks": "pass",
        "approvals": 0,
        "title": "t",
        "draft": False,
    }
    monkeypatch.setattr(
        "decky.server.views.github.load_pr_lists",
        lambda: ({"review": [row], "team": [], "mine": []}, []),
    )
    res = client.get("/api/tables/review")
    assert res.status_code == 200
    body = res.json()
    assert body["rows"][0]["url"] == "https://github.com/o/r/pull/1"


def test_review_action(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(pr_cmd, "open_review", lambda slug, n: calls.append((slug, n)))
    res = client.post("/api/prs/review", json={"repo": "o/r", "number": 2})
    assert res.status_code == 200
    assert calls == [("o/r", 2)]


def test_queue_disabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "decky.server.api.load_queue",
        lambda: {"disabled": True},
    )
    assert client.get("/api/queue").json() == {"disabled": True}


def test_review_failure_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import click

    def fail(*a):
        raise click.ClickException("nope")

    monkeypatch.setattr(pr_cmd, "open_review", fail)
    res = client.post("/api/prs/review", json={"repo": "o/r", "number": 1})
    assert res.status_code == 422
    assert res.json()["message"] == "nope"


def test_open_url(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("decky.server.api.open_http_url", lambda url: opened.append(url))
    res = client.post("/api/open-url", json={"url": "http://127.0.0.1:4387/session/ab"})
    assert res.status_code == 200
    assert opened == ["http://127.0.0.1:4387/session/ab"]


def test_open_url_bad_scheme(client: TestClient) -> None:
    res = client.post("/api/open-url", json={"url": "file:///etc/passwd"})
    assert res.status_code == 400


def test_spa_missing_503(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 503
    assert "pnpm -C web" in res.text


def test_dev_no_spa(client: TestClient) -> None:
    dev = TestClient(create_app(static=None, host="127.0.0.1"))
    assert dev.get("/").status_code == 404


def test_host_check_421(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr_cmd, "open_review", lambda *a: None)
    res = client.post(
        "/api/prs/review",
        json={"repo": "o/r", "number": 1},
        headers={"Host": "evil.example"},
    )
    assert res.status_code == 421


def test_config_roundtrip(client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("DECKY_CONFIG", str(path))
    res = client.get("/api/config")
    assert res.status_code == 200
    assert "settings" in res.json()
    put = client.put("/api/config/work_org", json={"value": "my-org"})
    assert put.status_code == 200
    delete = client.delete("/api/config/work_org")
    assert delete.status_code == 200

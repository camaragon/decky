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
    return TestClient(
        create_app(host="127.0.0.1", static=empty_static), base_url="http://127.0.0.1"
    )


def test_meta(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pr_cmd.config,
        "resolve",
        lambda key: ("x", "file") if key == "review.command" else (None, "unset"),
    )
    res = client.get("/api/meta")
    assert res.status_code == 200
    assert res.json()["reviewConfigured"] is True


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
        lambda: ({"review": [row], "team": [], "mine": []}, {"review": [], "team": [], "mine": []}),
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


def test_review_failure_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import click

    def fail(*a):
        raise click.ClickException("nope")

    monkeypatch.setattr(pr_cmd, "open_review", fail)
    res = client.post("/api/prs/review", json={"repo": "o/r", "number": 1})
    assert res.status_code == 422
    assert res.json()["message"] == "nope"


def test_open_url(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        "decky.server.api.open_http_url", lambda url: opened.append(url)
    )
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


def test_spa_icon_assets(tmp_path: Path) -> None:
    import shutil

    public = Path(__file__).parents[1] / "web" / "public"
    shutil.copytree(public, tmp_path, dirs_exist_ok=True)
    (tmp_path / "index.html").write_text("<html>decky</html>")
    client = TestClient(create_app(static=tmp_path, host="127.0.0.1"))

    for name in ("favicon.svg", "site.webmanifest"):
        response = client.get(f"/{name}")
        assert response.status_code == 200
        assert response.content == (public / name).read_bytes()


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


def test_config_roundtrip(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("DECKY_CONFIG", str(path))
    res = client.get("/api/config")
    assert res.status_code == 200
    assert "settings" in res.json()
    put = client.put("/api/config/work_org", json={"value": "my-org"})
    assert put.status_code == 200
    delete = client.delete("/api/config/work_org")
    assert delete.status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/config"),
        ("GET", "/api/meta"),
        ("GET", "/api/queue"),
        ("GET", "/api/tables/review"),
        ("PUT", "/api/config/work_org"),
        ("DELETE", "/api/config/work_org"),
        ("POST", "/api/prs/review"),
        ("POST", "/api/open-url"),
        ("GET", "/api/docs"),
        ("GET", "/api/openapi.json"),
        ("HEAD", "/api/config"),
        ("OPTIONS", "/api/config"),
    ],
)
def test_foreign_host_rejected_before_work(client, monkeypatch, method, path) -> None:
    def unexpected(*args, **kwargs):
        pytest.fail("untrusted request reached application work")

    monkeypatch.setattr("decky.config.load_file", unexpected)
    monkeypatch.setattr("decky.server.api.load_queue", unexpected)
    monkeypatch.setattr("decky.server.views.github.load_pr_lists", unexpected)
    monkeypatch.setattr(pr_cmd, "open_review", unexpected)
    monkeypatch.setattr("decky.server.api.open_http_url", unexpected)
    response = client.request(
        method,
        path,
        headers={"Host": "foreign.example"},
        json={
            "value": "example",
            "repo": "o/r",
            "number": 1,
            "url": "https://example.com",
        },
    )
    assert response.status_code == 421


@pytest.mark.parametrize(
    "host", ["127.0.0.1:8777", "LOCALHOST", "[::1]", "[::1]:8777", "[0:0:0:0:0:0:0:1]"]
)
def test_loopback_host_config_write(tmp_path, monkeypatch, host) -> None:
    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    client = TestClient(create_app(host="::1"), base_url="http://[::1]:8777")
    response = client.put(
        "/api/config/work_org", headers={"Host": host}, json={"value": "example"}
    )
    assert response.status_code == 200
    assert pr_cmd.config.load_file()["work_org"] == "example"


@pytest.mark.parametrize(
    "host",
    [
        "[::1",
        "[::1]extra",
        "localhost:bad",
        "localhost:",
        "foreign.example",
        "foreign.example@localhost",
        "localhost/path",
        "::1",
    ],
)
def test_invalid_host_rejected(client, host) -> None:
    assert client.get("/api/config", headers={"Host": host}).status_code == 421


def test_proxy_read_responses_hide_credentials(tmp_path, monkeypatch):
    import click
    from decky import config

    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("DECKY_SERVER_ALLOWED_HOSTS", "review.example.com")
    secret = "example-secret-value"
    for key, setting in config.SETTINGS.items():
        if key.endswith((".command", "_command")):
            value = f'["tool", "--token", "{secret}"]' if setting.kind == "list_str" else f"tool --token {secret}"
            monkeypatch.setenv(setting.env, value)
    monkeypatch.setenv("DECKY_JIRA_BROWSE_URL", f"https://user:{secret}@tracker.example/{{key}}?token={secret}")
    # Invalid values must not fall back to exposing raw config or parser errors.
    monkeypatch.setenv("DECKY_REVIEW_REVIEWER_COMMAND", f'["{secret}",')
    app = create_app(static=None)
    proxy = TestClient(app, base_url="https://review.example.com")
    for path in ("/api/meta", "/api/config"):
        response = proxy.get(path)
        assert response.status_code == 200
        assert secret not in response.text
    settings = {s["key"]: s for s in proxy.get("/api/config").json()["settings"]}
    assert settings["pr.hide_authors"]["value"] == '["renovate"]'
    assert settings["review.command"]["value"] == "[hidden through an allowed proxy host]"
    assert proxy.get("/api/meta").json()["jiraBrowseUrl"] is None
    local = TestClient(app, base_url="http://127.0.0.1")
    assert secret in local.get("/api/config").text
    assert secret in local.get("/api/meta").json()["jiraBrowseUrl"]

    def fail():
        raise click.ClickException(secret)

    monkeypatch.setattr("decky.server.api.load_queue", fail)
    response = proxy.get("/api/queue")
    assert response.status_code == 422
    assert secret not in response.text


def test_proxy_meta_returns_plain_issue_url_template(tmp_path, monkeypatch):
    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("DECKY_SERVER_ALLOWED_HOSTS", "review.example.com")
    template = "https://tracker.example/browse/{key}"
    monkeypatch.setenv("DECKY_JIRA_BROWSE_URL", template)
    proxy = TestClient(create_app(static=None), base_url="https://review.example.com")
    assert proxy.get("/api/meta").json()["jiraBrowseUrl"] == template
    settings = {s["key"]: s for s in proxy.get("/api/config").json()["settings"]}
    assert settings["jira.browse_url"]["value"] == template

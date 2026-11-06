"""MCP tools on decky server."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError

from decky.commands import pr as pr_cmd
from decky import config
from decky.server import app as app_mod
from decky.server import mcp
from decky.server.api import State

HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-06-18",
}


def call(server, name: str, **args):
    return asyncio.run(server.call_tool(name, args))


def test_list_prs(monkeypatch: pytest.MonkeyPatch) -> None:
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
        "decky.server.mcp.github.load_pr_lists",
        lambda: ({"review": [row], "team": [], "mine": []}, {"review": [], "team": [], "mine": []}),
    )
    out = mcp.list_prs("review")
    assert out["rows"][0]["url"] == "https://github.com/o/r/pull/1"


def test_start_review(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(pr_cmd, "open_review", lambda slug, n: calls.append((slug, n)))
    state = State()
    mcp.start_review(state, "o/r", 2)
    assert calls == [("o/r", 2)]


def test_get_config_unknown() -> None:
    with pytest.raises(ToolError):
        mcp.get_config("no.such.key")


def test_set_and_list_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.toml"
    monkeypatch.setenv("DECKY_CONFIG", str(cfg))
    assert mcp.set_config(State(), "work_org", "my-org").startswith("saved")
    listed = mcp.list_config()
    assert any(s["key"] == "work_org" for s in listed)


def test_mcp_host_421() -> None:
    with TestClient(
        app_mod.create_app(host="127.0.0.1"), base_url="http://127.0.0.1"
    ) as client:
        res = client.post(
            "/mcp", headers={**HEADERS, "Host": "evil.example"}, json={"jsonrpc": "2.0"}
        )
    assert res.status_code == 421


@pytest.mark.parametrize("second_interface", ["mcp", "http"])
@pytest.mark.parametrize("unset", [False, True])
def test_concurrent_config_mutations(
    tmp_path, monkeypatch, second_interface, unset
) -> None:
    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    config.set_value("work_org", "old")
    first_saved = threading.Event()
    release_first = threading.Event()
    second_read = threading.Event()
    second_attempt = threading.Event()

    class ObservedLock:
        def __init__(self):
            self.lock = threading.RLock()

        def __enter__(self):
            if first_saved.is_set():
                second_attempt.set()
            self.lock.acquire()

        def __exit__(self, *args):
            self.lock.release()

    shared = State(lock=ObservedLock())
    server = mcp.build(shared)
    client = TestClient(app_mod.create_app(state=shared), base_url="http://127.0.0.1")
    load_file, save_file = config.load_file, config.save_file

    def observed_load():
        if first_saved.is_set():
            second_read.set()
        return load_file()

    def held_save(data):
        if not first_saved.is_set():
            first_saved.set()
            assert release_first.wait(3), "first write was never released"
        save_file(data)

    def second_mutation():
        if second_interface == "http":
            response = client.put("/api/config/pr.dir", json={"value": "~/reviews"})
            assert response.status_code == 200
        else:
            call(server, "set_config_tool", key="pr.dir", value="~/reviews")

    monkeypatch.setattr(config, "load_file", observed_load)
    monkeypatch.setattr(config, "save_file", held_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            call,
            server,
            "unset_config_tool" if unset else "set_config_tool",
            **({"key": "work_org"} if unset else {"key": "work_org", "value": "new"}),
        )
        try:
            assert first_saved.wait(3)
            second = pool.submit(second_mutation)
            assert second_attempt.wait(1), "second mutation bypassed the shared lock"
            assert not second_read.is_set(), (
                "second mutation read an uncommitted snapshot"
            )
        finally:
            release_first.set()
        first.result(timeout=3)
        second.result(timeout=3)
    data = load_file()
    assert data.get("work_org") == (None if unset else "new")
    assert data["pr"]["dir"] == "~/reviews"


def test_failed_config_write_releases_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    config.set_value("work_org", "old")
    shared = State()
    server = mcp.build(shared)

    with monkeypatch.context() as failure:

        def fail_replace(*args):
            raise OSError("cannot replace config")

        failure.setattr("decky.config.os.replace", fail_replace)
        with pytest.raises(ToolError, match="Error executing tool set_config_tool"):
            call(server, "set_config_tool", key="work_org", value="new")
    assert config.load_file() == {"work_org": "old"}
    client = TestClient(app_mod.create_app(state=shared), base_url="http://127.0.0.1")

    def can_acquire_lock():
        acquired = shared.lock.acquire(timeout=1)
        if acquired:
            shared.lock.release()
        return acquired

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(can_acquire_lock).result(timeout=3)
        response = pool.submit(
            client.put, "/api/config/pr.dir", json={"value": "~/reviews"}
        ).result(timeout=3)
    assert response.status_code == 200
    assert config.load_file() == {"work_org": "old", "pr": {"dir": "~/reviews"}}

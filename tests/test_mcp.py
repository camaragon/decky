"""MCP tools on decky server."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError

from decky.commands import pr as pr_cmd
from decky.server import app as app_mod
from decky.server import mcp
from decky.server.api import State

HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


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
        lambda: ({"review": [row], "team": [], "mine": []}, []),
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
    assert mcp.set_config("work_org", "my-org").startswith("saved")
    listed = mcp.list_config()
    assert any(s["key"] == "work_org" for s in listed)


def test_mcp_host_421() -> None:
    with TestClient(app_mod.create_app(host="127.0.0.1"), base_url="http://127.0.0.1") as client:
        res = client.post("/mcp", headers={**HEADERS, "Host": "evil.example"}, json={"jsonrpc": "2.0"})
    assert res.status_code == 421

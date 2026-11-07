"""Inbox scoping, attachment boundaries, and decision delivery."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from decky.server import inbox
from decky.server.app import create_app


@pytest.fixture
def setup(monkeypatch):
    settings = {"review.owners": ["example-org"], "review.decision_command": ["example-hook", "--stdin"]}
    monkeypatch.setattr(inbox.config, "resolve", lambda key: (settings.get(key), "file"))
    client = TestClient(create_app(static=None), base_url="http://127.0.0.1")
    return settings, client


def row(number, base="main", head=None, repo="example-org/example-repo"):
    return {"repo": repo, "number": number, "base_branch": base, "head_branch": head or f"branch-{number}",
            "head_sha": f"sha-{number}", "url": f"https://github.com/{repo}/pull/{number}", "body": "", "image_urls": []}


def test_scoped_queries_and_no_owners(setup, monkeypatch):
    settings, client = setup
    query = Mock(return_value={"data": {"search": {"nodes": [], "pageInfo": {"hasNextPage": False}}}})
    monkeypatch.setattr(inbox.github, "_gh_json", query)
    settings["review.owners"] = []
    assert client.get("/api/inbox").json()["stacks"] == []
    query.assert_not_called()
    settings["review.owners"] = ["example-org", "example-user"]
    assert client.get("/api/inbox").status_code == 200
    assert query.call_count == 2
    for call, owner in zip(query.call_args_list, settings["review.owners"]):
        assert f"q=is:pr is:open author:@me user:{owner}" in call.args
        assert "review-requested" not in " ".join(call.args)
    settings["review.owners"] = ["example-org author:someone"]
    assert client.get("/api/inbox").status_code == 422
    assert query.call_count == 2


def test_stacks_merge_order():
    grouped = inbox.stacks([row(3, "branch-2"), row(7), row(2, "branch-1"), row(1), row(1, repo="example-user/example-repo")])
    assert [[p["number"] for p in s["prs"]] for s in grouped] == [[1, 2, 3], [7], [1]]


@pytest.mark.parametrize("url", ["https://evil.example/image.png", "http://github.com/a.png", "https://github.com/unlisted.png", "https://github.com@evil.example/image.png"])
def test_image_refuses_non_pr_urls(setup, monkeypatch, url):
    _, client = setup
    p = row(1)
    p["image_urls"] = ["https://github.com/allowed.png", "https://evil.example/image.png"]
    client.app.state.decky.inbox_rows = {(p["repo"], 1): p}
    fetch = Mock(side_effect=AssertionError("must not fetch credentials"))
    monkeypatch.setattr(inbox.github, "run_gh", fetch)
    assert client.get("/api/inbox/image", params={"repo": p["repo"], "number": 1, "url": url}).status_code == 403
    fetch.assert_not_called()


def test_decision_payload_and_stale_head(setup, monkeypatch):
    _, client = setup
    prs = [row(1), row(2, "branch-1")]
    monkeypatch.setattr(inbox, "load", lambda: {"stacks": [{"repo": prs[0]["repo"], "prs": prs}]})
    command = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(inbox, "run_command", command)
    answer = {"repo": prs[0]["repo"], "numbers": [1, 2], "head_shas": ["sha-1", "sha-2"], "scope": "stack", "decision": "hold", "note": "Please explain the change"}
    assert client.post("/api/inbox/decision", json=answer).status_code == 200
    assert command.call_args.args[0] == ["example-hook", "--stdin"]
    payload = json.loads(command.call_args.kwargs["input"])
    assert payload == {"version": 1, "decision": "hold", "scope": "stack", "repo": prs[0]["repo"], "prs": [{k: p[k] for k in ("number", "url", "head_sha")} for p in prs], "note": answer["note"]}
    answer["head_shas"] = ["old", "sha-2"]
    assert client.post("/api/inbox/decision", json=answer).status_code == 409
    assert command.call_count == 1


def test_proxy_host_requires_exact_configured_name(setup, monkeypatch):
    settings, _ = setup
    settings["server.allowed_hosts"] = ["review.example.com"]
    client = TestClient(create_app(static=None))
    monkeypatch.setattr(inbox, "load", lambda: {"stacks": []})
    assert client.get("/api/inbox", headers={"Host": "review.example.com"}).status_code == 200
    assert client.get("/api/inbox", headers={"Host": "other.example.com"}).status_code == 421
    assert client.get("/api/inbox", headers={"Host": "review.example.com.evil.example"}).status_code == 421

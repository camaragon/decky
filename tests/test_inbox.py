"""Inbox scoping, attachment boundaries, and decision delivery."""
import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from types import SimpleNamespace
from unittest.mock import Mock, call

import click
import pytest
from fastapi.testclient import TestClient

from decky.server import api, inbox
from decky.server.app import create_app


@pytest.fixture
def setup(monkeypatch):
    settings = {"review.owners": ["example-org"], "review.decision_command": ["example-hook", "--stdin"]}
    monkeypatch.setattr(inbox.config, "resolve", lambda key: (settings.get(key), "file"))
    client = TestClient(create_app(static=None), base_url="http://127.0.0.1")
    return settings, client


def row(number, base="main", head=None, repo="example-org/example-repo", fork=False):
    return {"repo": repo, "number": number, "base_branch": base, "head_branch": head or f"branch-{number}", "cross_repository": fork,
            "head_sha": f"sha-{number}", "url": f"https://github.com/{repo}/pull/{number}", "body": "", "image_urls": []}


def test_scoped_queries_and_no_owners(setup, monkeypatch):
    settings, client = setup
    query = Mock(return_value={"data": {"search": {"nodes": [], "pageInfo": {"hasNextPage": False}}}})
    monkeypatch.setattr(inbox.github, "_gh_json", query)
    settings["review.owners"] = []
    assert client.get("/api/inbox").json()["stacks"] == []
    query.assert_not_called()
    settings.update({"review.owners": ["example-org", "example-user"], "review.all_owners": False, "review.exclude_owners": ["example-org"]})
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


def test_fork_head_does_not_join_stack():
    grouped = inbox.stacks([row(5, head="main", fork=True), row(6), row(7, "branch-6")])
    assert [[p["number"] for p in s["prs"]] for s in grouped] == [[5], [6, 7]]


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
    monkeypatch.setattr(inbox, "search", lambda owner, repo=None: (prs, []))
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


def test_decision_queries_only_answer_repo(setup, monkeypatch):
    settings, client = setup
    settings["review.owners"] = ["example-org", "example-user"]
    nodes = [{"number": n, "repository": {"nameWithOwner": repo}} for n, repo in
             [(1, "example-org/example-repo"), (9, "example-org/other-repo"), (2, "example-org/example-repo")]]
    query = Mock(return_value={"data": {"search": {"nodes": nodes, "pageInfo": {"hasNextPage": False}}}})
    monkeypatch.setattr(inbox.github, "_gh_json", query)

    def load_pr(repo, number):
        if repo != "example-org/example-repo":
            raise click.ClickException("unrelated repo failed")
        return {**row(number, "branch-1" if number == 2 else "main"), "body": ""}, []
    monkeypatch.setattr(inbox.github, "load_pr", load_pr)
    command = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(inbox, "run_command", command)
    answer = {"repo": "example-org/example-repo", "numbers": [1, 2], "head_shas": ["sha-1", "sha-2"], "scope": "stack", "decision": "merge"}
    assert client.post("/api/inbox/decision", json=answer).status_code == 200
    assert query.call_count == 1
    assert "q=is:pr is:open author:@me user:example-org repo:example-org/example-repo" in query.call_args.args
    assert [p["number"] for p in json.loads(command.call_args.kwargs["input"])["prs"]] == [1, 2]
    answer["numbers"], answer["head_shas"] = [2, 1], ["sha-2", "sha-1"]
    assert client.post("/api/inbox/decision", json=answer).status_code == 409
    for repo in ["example-other/example-repo", "example-org/example-repo author:someone"]:
        assert client.post("/api/inbox/decision", json={**answer, "repo": repo}).status_code in (400, 403)
    assert query.call_count == 2
    assert command.call_count == 1


def test_proxy_host_requires_exact_configured_name(setup, monkeypatch):
    settings, _ = setup
    settings["server.allowed_hosts"] = ["review.example.com"]
    client = TestClient(create_app(static=None))
    monkeypatch.setattr(inbox, "load", lambda: {"stacks": []})
    assert client.get("/api/inbox", headers={"Host": "review.example.com"}).status_code == 200
    assert client.get("/api/inbox", headers={"Host": "other.example.com"}).status_code == 421
    assert client.get("/api/inbox", headers={"Host": "review.example.com.evil.example"}).status_code == 421


def test_invalid_allowed_host_fails_startup(setup):
    settings, _ = setup
    settings["server.allowed_hosts"] = ["review.example.com:443"]
    with pytest.raises(click.ClickException, match="exact hostnames"):
        create_app(static=None)


def test_proxy_host_only_reaches_inbox(setup, monkeypatch, tmp_path):
    settings, _ = setup
    settings["server.allowed_hosts"] = ["review.example.com"]
    (tmp_path / "index.html").write_text("<html></html>")
    app = create_app(static=tmp_path)
    save = Mock(return_value="saved")
    app.state.decky.save_setting = save
    opened = Mock()
    monkeypatch.setattr(api, "open_http_url", opened)
    prs = [row(1)]
    monkeypatch.setattr(inbox, "search", lambda owner, repo=None: (prs, []))
    command = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(inbox, "run_command", command)
    answer = {"repo": prs[0]["repo"], "numbers": [1], "head_shas": ["sha-1"], "scope": "pr", "decision": "merge"}
    proxy = TestClient(app, base_url="http://review.example.com")
    assert proxy.put("/api/config/review.command", json={"value": "evil {url}"}).status_code == 403
    assert proxy.delete("/api/config/review.command").status_code == 403
    assert proxy.get("/api/config").status_code == 403
    assert proxy.post("/api/open-url", json={"url": "https://example.com"}).status_code == 403
    assert proxy.post("/api/prs/review", json={"repo": prs[0]["repo"], "number": 1}).status_code == 403
    assert proxy.post("/mcp", json={}).status_code == 403
    save.assert_not_called()
    opened.assert_not_called()
    assert proxy.get("/inbox").status_code == 200
    assert proxy.get("/api/inbox").status_code == 200
    assert proxy.post("/api/inbox/decision", json=answer).status_code == 200
    assert command.call_count == 1
    local = TestClient(app, base_url="http://127.0.0.1")
    assert local.put("/api/config/review.command", json={"value": "agent {url}"}).status_code == 200
    assert local.post("/api/open-url", json={"url": "https://example.com"}).status_code == 200
    save.assert_called_once_with("review.command", "agent {url}")
    opened.assert_called_once_with("https://example.com")
    assert local.post("/api/inbox/decision", json=answer).status_code == 200


PNG = b"\x89PNG\r\n\x1a\n" + b"example-image"


@pytest.mark.parametrize("prefix,suffix", [("https://github.com/", "/blob/"),
                                           ("https://github.com/", "/raw/"),
                                           ("https://raw.githubusercontent.com/", "/")])
@pytest.mark.parametrize("ref", ["main", "feature/screenshots"])
def test_repository_image_uses_contents_api(setup, monkeypatch, prefix, suffix, ref):
    _, client = setup
    p = row(1)
    url = f"{prefix}{p['repo']}{suffix}{ref}/docs/screen.png"
    if suffix == "/blob/":
        url += "?raw=true"
    p["image_urls"] = [url]
    client.app.state.decky.inbox_rows = {(p["repo"], 1): p}
    monkeypatch.setattr(inbox.github, "run_gh", Mock(return_value=SimpleNamespace(returncode=0, stdout="example-token\n")))
    headers = Message()
    headers["Content-Type"] = "application/vnd.github.raw; charset=utf-8"
    upstream = BytesIO(PNG)
    upstream.headers = headers
    calls = []

    def fetch(request, timeout):
        calls.append(request)
        assert timeout == 15
        from urllib.parse import quote_plus
        target = f"https://api.github.com/repos/{p['repo']}/contents/docs/screen.png?ref={quote_plus(ref)}"
        if request.full_url != target:
            raise HTTPError(request.full_url, 404, "Not Found", Message(), BytesIO())
        return upstream

    monkeypatch.setattr(inbox, "build_opener", lambda *args: SimpleNamespace(open=fetch))
    response = client.get("/api/inbox/image", params={"repo": p["repo"], "number": 1, "url": url})
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(calls) == 2
    assert all(call.get_header("Authorization") == "Bearer example-token" for call in calls)
    assert all(call.get_header("Accept") == "application/vnd.github.raw" for call in calls)


@pytest.mark.parametrize("url", [
    "https://github.com/example-org/other-repo/blob/main/screen.png?raw=true",
    "https://github.com/example-user/example-repo/raw/main/screen.png",
    "https://raw.githubusercontent.com/example-org/other-repo/main/screen.png",
])
def test_repository_image_refuses_other_repository(setup, monkeypatch, url):
    _, client = setup
    p = row(1)
    p["image_urls"] = [url]
    client.app.state.decky.inbox_rows = {(p["repo"], 1): p}
    credentials = Mock(side_effect=AssertionError("must not fetch credentials"))
    monkeypatch.setattr(inbox.github, "run_gh", credentials)
    assert client.get("/api/inbox/image", params={"repo": p["repo"], "number": 1, "url": url}).status_code == 403
    credentials.assert_not_called()


@pytest.mark.parametrize("body,status", [(b"<svg xmlns='http://www.w3.org/2000/svg'/>", 415),
                                         (PNG.ljust(10 * 1024 * 1024 + 1, b"x"), 413)])
def test_repository_image_preserves_raster_and_size_limits(setup, monkeypatch, body, status):
    _, client = setup
    p = row(1)
    url = f"https://github.com/{p['repo']}/blob/main/screen.png"
    p["image_urls"] = [url]
    client.app.state.decky.inbox_rows = {(p["repo"], 1): p}
    monkeypatch.setattr(inbox.github, "run_gh", Mock(return_value=SimpleNamespace(returncode=0, stdout="example-token")))
    headers = Message()
    headers["Content-Type"] = "application/vnd.github.raw; charset=utf-8"
    upstream = BytesIO(body)
    upstream.headers = headers
    monkeypatch.setattr(inbox, "build_opener", lambda *args: SimpleNamespace(open=lambda *args, **kwargs: upstream))
    assert client.get("/api/inbox/image", params={"repo": p["repo"], "number": 1, "url": url}).status_code == status


@pytest.mark.parametrize("body,kind", [(b"\xff\xd8\xff\xe0example", "image/jpeg"),
                                       (b"GIF89aexample", "image/gif"),
                                       (b"RIFF\x00\x00\x00\x00WEBPexample", "image/webp"),
                                       (b"\x00\x00\x00\x1cftypavifexample", "image/avif")])
def test_repository_image_serves_detected_raster_type(setup, monkeypatch, body, kind):
    _, client = setup
    p = row(1)
    url = f"https://raw.githubusercontent.com/{p['repo']}/main/screen.img"
    p["image_urls"] = [url]
    client.app.state.decky.inbox_rows = {(p["repo"], 1): p}
    monkeypatch.setattr(inbox.github, "run_gh", Mock(return_value=SimpleNamespace(returncode=0, stdout="example-token")))
    headers = Message()
    headers["Content-Type"] = "application/vnd.github.raw; charset=utf-8"
    upstream = BytesIO(body)
    upstream.headers = headers
    monkeypatch.setattr(inbox, "build_opener", lambda *args: SimpleNamespace(open=lambda *args, **kwargs: upstream))
    response = client.get("/api/inbox/image", params={"repo": p["repo"], "number": 1, "url": url})
    assert response.status_code == 200
    assert response.headers["content-type"] == kind


def test_all_owners_search_excludes_before_details_and_paginates(setup, monkeypatch):
    settings, client = setup
    settings.update({"review.all_owners": True, "review.exclude_owners": ["EXAMPLE-ORG", "example-excluded"]})
    query = Mock(side_effect=[
        {"data": {"search": {"nodes": [
            {"number": 9, "repository": {"nameWithOwner": "Example-Org/example-repo"}},
            {"number": 1, "repository": {"nameWithOwner": "example-user/example-repo"}},
        ], "pageInfo": {"hasNextPage": True, "endCursor": "next-page"}}}},
        {"data": {"search": {"nodes": [
            {"number": 2, "repository": {"nameWithOwner": "example-user/example-repo"}},
            {"number": 3, "repository": {"nameWithOwner": "example-other/example-repo"}},
        ], "pageInfo": {"hasNextPage": False}}}},
    ])
    monkeypatch.setattr(inbox.github, "_gh_json", query)
    details = Mock(side_effect=lambda repo, number: (row(number, "branch-1" if number == 2 else "main", repo=repo), []))
    monkeypatch.setattr(inbox.github, "load_pr", details)
    response = client.get("/api/inbox")
    assert response.status_code == 200
    assert [[p["number"] for p in s["prs"]] for s in response.json()["stacks"]] == [[3], [1, 2]]
    assert query.call_count == 2
    for call in query.call_args_list:
        assert "q=is:pr is:open author:@me -user:example-org -user:example-excluded" in call.args
    assert "cursor=next-page" in query.call_args_list[1].args
    assert details.call_args_list == [
        call("example-user/example-repo", 1),
        call("example-user/example-repo", 2),
        call("example-other/example-repo", 3),
    ]


def test_all_owners_without_configured_owners_uses_one_search(setup, monkeypatch):
    settings, client = setup
    settings.update({"review.owners": [], "review.all_owners": True})
    query = Mock(return_value={"data": {"search": {"nodes": [], "pageInfo": {"hasNextPage": False}}}})
    monkeypatch.setattr(inbox.github, "_gh_json", query)
    response = client.get("/api/inbox")
    assert response.status_code == 200
    assert response.json()["all_owners"] is True
    query.assert_called_once()
    assert "q=is:pr is:open author:@me" in query.call_args.args


def test_all_owners_decision_authorization(setup, monkeypatch):
    settings, client = setup
    settings.update({"review.all_owners": True, "review.exclude_owners": ["EXAMPLE-ORG"]})
    p = row(1, repo="example-user/example-repo")
    query = Mock(return_value={"data": {"search": {"nodes": [
        {"number": 1, "repository": {"nameWithOwner": p["repo"]}},
    ], "pageInfo": {"hasNextPage": False}}}})
    monkeypatch.setattr(inbox.github, "_gh_json", query)
    details = Mock(return_value=(p, []))
    monkeypatch.setattr(inbox.github, "load_pr", details)
    command = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(inbox, "run_command", command)
    answer = {"repo": p["repo"], "numbers": [1], "head_shas": ["sha-1"], "scope": "pr", "decision": "hold"}
    assert client.post("/api/inbox/decision", json=answer).status_code == 200
    assert "q=is:pr is:open author:@me -user:example-org repo:example-user/example-repo" in query.call_args.args
    assert client.post("/api/inbox/decision", json={**answer, "repo": "example-org/example-repo"}).status_code == 403
    query.assert_called_once()
    details.assert_called_once()
    command.assert_called_once()


@pytest.mark.parametrize("all_owners,owner,status", [
    (True, "example-user", 200), (True, "Example-Org", 403),
    (False, "example-user", 403), (False, "example-org", 200),
])
def test_image_owner_authorization(setup, monkeypatch, all_owners, owner, status):
    settings, client = setup
    settings.update({"review.all_owners": all_owners, "review.exclude_owners": ["example-org"]})
    p = row(1, repo=f"{owner}/example-repo")
    url = "https://github.com/allowed.png"
    p["image_urls"] = [url]
    client.app.state.decky.inbox_rows = {(p["repo"], 1): p}
    credentials = Mock(return_value=SimpleNamespace(returncode=0, stdout="example-token"))
    monkeypatch.setattr(inbox.github, "run_gh", credentials)
    upstream = Mock()
    upstream.headers.get_content_type.return_value = "image/png"
    upstream.read.return_value = b"example-image"
    upstream.__enter__ = Mock(return_value=upstream)
    upstream.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = upstream
    monkeypatch.setattr(inbox, "build_opener", Mock(return_value=opener))
    response = client.get("/api/inbox/image", params={"repo": p["repo"], "number": 1, "url": url})
    assert response.status_code == status
    assert credentials.call_count == (1 if status == 200 else 0)
    assert opener.open.call_count == (1 if status == 200 else 0)


def test_invalid_exclusion_rejected_before_search(setup, monkeypatch):
    settings, client = setup
    settings.update({"review.all_owners": True, "review.exclude_owners": ["example-org author:someone"]})
    query = Mock()
    monkeypatch.setattr(inbox.github, "_gh_json", query)
    assert client.get("/api/inbox").status_code == 422
    query.assert_not_called()

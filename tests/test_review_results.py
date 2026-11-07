"""Local result format and inbox intent scenarios."""

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from decky.server import inbox, review_results
from decky.server.app import create_app

SHA = "a" * 40
REPO = "example/demo"


@pytest.fixture
def result():
    return {"version": 1, "head_sha": SHA, "risk": "medium",
            "summary": {"what_changed": "Add an export button.", "why": "Save reports locally.",
                        "what_to_check": "Try an empty report."},
            "reviewer": "Primary reviewer", "generated_at": "2026-11-07T12:00:00Z",
            "second_opinion": {"reviewer": "Second reviewer", "risk": "high",
                               "summary": "Check the exported fields."}}


def write_result(directory, result):
    path = directory / "example+demo-1.json"
    path.write_text(json.dumps(result))
    return path


@pytest.mark.parametrize("mode", ["current", "outdated", "missing", "malformed", "disabled"])
def test_inbox_local_result(mode, tmp_path, monkeypatch, result):
    settings = {"review.owners": ["example"], "review.results_dir": str(tmp_path)}
    monkeypatch.setattr(inbox.config, "resolve", lambda key: (settings.get(key), "file"))
    row = {"repo": REPO, "number": 1, "head_sha": SHA, "head_branch": "feature",
           "base_branch": "main", "cross_repository": False}
    monkeypatch.setattr(inbox, "search", lambda owner: ([row], []))
    network = Mock(side_effect=AssertionError("results must not use GitHub"))
    monkeypatch.setattr(inbox.github, "_gh_json", network)
    if mode != "missing":
        path = write_result(tmp_path, result)
        if mode == "malformed":
            path.write_text("{broken")
    if mode == "outdated":
        row["head_sha"] = "b" * 40
    if mode == "disabled":
        settings["review.results_dir"] = None
    response = TestClient(create_app(static=None), base_url="http://127.0.0.1").get("/api/inbox")
    assert response.status_code == 200
    pr = response.json()["stacks"][0]["prs"][0]
    if mode in ("current", "outdated"):
        assert pr["review_result"] == {**result, "outdated": mode == "outdated"}
    else:
        assert "review_result" not in pr
    network.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("version", 2), ("version", True), ("version", 1.0),
    ("risk", "critical"), ("head_sha", "short"),
    ("reviewer", " "), ("generated_at", "yesterday"),
    ("generated_at", "2026-11-07T12:00:00"), ("summary", {"why": "Missing fields"}),
    ("second_opinion", {"reviewer": "Second", "risk": "low", "summary": ""}),
])
def test_parser_ignores_invalid_format(tmp_path, result, field, value):
    write_result(tmp_path, {**result, field: value})
    assert review_results.load(str(tmp_path), REPO, 1, SHA) is None


def test_optional_second_opinion_and_unknown_fields(tmp_path, result):
    result.pop("second_opinion")
    write_result(tmp_path, {**result, "future_field": "ignored"})
    parsed = review_results.load(str(tmp_path), "Example/Demo", 1, SHA.upper())
    assert parsed == {**result, "second_opinion": None, "outdated": False}


def test_reader_confines_reads_and_ignores_non_files(tmp_path, result, monkeypatch):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(result))
    directory = tmp_path / "results"
    directory.mkdir()
    path = directory / "example+demo-1.json"
    path.symlink_to(outside)
    assert review_results.load(str(directory), REPO, 1, SHA) is None
    path.unlink()
    path.mkdir()
    assert review_results.load(str(directory), REPO, 1, SHA) is None
    opened = Mock(side_effect=PermissionError)
    monkeypatch.setattr(review_results.os, "open", opened)
    for repo, number in [("../outside", 1), ("example/../../outside", 1), (REPO, -1)]:
        assert review_results.load(str(directory), repo, number, SHA) is None
    opened.assert_not_called()
    assert review_results.load(str(directory), REPO, 1, SHA) is None


def test_reader_ignores_oversized_files(tmp_path):
    (tmp_path / "example+demo-1.json").write_bytes(b" " * (review_results.MAX_BYTES + 1))
    assert review_results.load(str(tmp_path), REPO, 1, SHA) is None

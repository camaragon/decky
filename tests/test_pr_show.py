"""Read-only PR detail JSON, pagination, images, and failure output."""

import json
import subprocess

import pytest
from click.testing import CliRunner

from decky import github
from decky.cli import cli
from tests.test_github import _node


@pytest.mark.parametrize("changed_files", [3, 3001])
def test_show_pages_files_and_checks_and_extracts_images(monkeypatch, changed_files):
    node = _node("example/api", 8)
    node.update(
        changedFiles=changed_files,
        headRefOid="abc123",
        body="""
![Preview](https://images.example/view.png "Title")
![Opaque](<https://images.example/render?id=1&size=2>)
![Reference][preview]
[preview]: https://images.example/reference
<img src="https://images.example/view.png">
<img src="https://images.example/html?a=1&amp;b=2">
https://github.com/user-attachments/assets/abc
https://images.example/raw.webp
![Local](./private.png)
[Ordinary link](https://example.com/page)
""",
    )
    endpoints = {
        "repos/example/api/pulls/8/files?per_page=100": [
            [{"filename": "a.py", "additions": 4, "deletions": 2}],
            [
                {"filename": "b.py", "additions": 0, "deletions": 1},
                {"filename": "c.py", "additions": 1, "deletions": 0},
            ],
        ],
        "repos/example/api/commits/abc123/check-runs?per_page=100": [
            {
                "check_runs": [
                    {
                        "name": "test",
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://example.com/check",
                    }
                ]
            },
            {
                "check_runs": [
                    {
                        "name": "lint",
                        "status": "queued",
                        "conclusion": None,
                        "html_url": None,
                    }
                ]
            },
        ],
        "repos/example/api/commits/abc123/status?per_page=100": [
            {
                "statuses": [
                    {"context": "deploy", "state": "pending", "target_url": None}
                ]
            },
            {
                "statuses": [
                    {
                        "context": "build",
                        "state": "success",
                        "target_url": "https://example.com/status",
                    }
                ]
            },
        ],
    }
    seen = []

    def fetch(*args):
        if args[1] == "graphql":
            data = {"data": {"repository": {"pullRequest": node}}}
        else:
            assert "--paginate" in args and "--slurp" in args
            seen.append(args[1])
            data = endpoints[args[1]]
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(data))

    monkeypatch.setattr(github, "run_gh", fetch)
    result = CliRunner().invoke(cli, ["pr", "show", "example/api", "8", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    row = data["pr"]
    assert data["version"] == 1
    assert data["notes"] == (
        []
        if changed_files == 3
        else ["changed files truncated by GitHub (maximum 3000)"]
    )
    assert row["body"] == node["body"] and row["changed_files"] == changed_files
    assert row["files"] == [
        {"path": "a.py", "additions": 4, "deletions": 2},
        {"path": "b.py", "additions": 0, "deletions": 1},
        {"path": "c.py", "additions": 1, "deletions": 0},
    ]
    assert row["check_runs"] == [
        {
            "name": "test",
            "status": "completed",
            "conclusion": "success",
            "url": "https://example.com/check",
        },
        {"name": "lint", "status": "queued", "conclusion": None, "url": None},
    ]
    assert row["commit_statuses"] == [
        {"name": "deploy", "state": "pending", "url": None},
        {"name": "build", "state": "success", "url": "https://example.com/status"},
    ]
    assert set(row["image_urls"]) == {
        "https://images.example/view.png",
        "https://images.example/render?id=1&size=2",
        "https://images.example/reference",
        "https://images.example/html?a=1&b=2",
        "https://github.com/user-attachments/assets/abc",
        "https://images.example/raw.webp",
    }
    assert len(row["image_urls"]) == 6 and set(seen) == set(endpoints)


@pytest.mark.parametrize("args", [["list"], ["show", "example/api", "8"]])
@pytest.mark.parametrize(
    "response",
    [
        subprocess.CompletedProcess([], 1, stderr="authentication required"),
        subprocess.CompletedProcess(
            [], 0, stdout='{"data":null,"errors":[{"message":"denied"}]}'
        ),
        subprocess.CompletedProcess([], 0, stdout="invalid JSON"),
    ],
)
def test_json_errors_emit_no_success_document(monkeypatch, args, response):
    monkeypatch.setattr(github, "run_gh", lambda *a: response)
    result = CliRunner().invoke(cli, ["pr", *args, "--json"])
    assert result.exit_code != 0
    assert result.stdout == "" and "Error:" in result.stderr

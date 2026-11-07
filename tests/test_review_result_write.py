"""Writer intent scenarios through the CLI with real fake-reviewer processes."""

import json
import stat
import subprocess
import sys

import pytest
import tomli_w
from click.testing import CliRunner

from decky import config, github
from decky.cli import cli
from decky.server.review_results import load

SHA = "a" * 40
SUMMARY = {"what_changed": "Add exports.", "why": "Save reports.", "what_to_check": "Try an empty report."}


@pytest.fixture
def writer(tmp_path, monkeypatch):
    for setting in config.SETTINGS.values():
        monkeypatch.delenv(setting.env, raising=False)
    monkeypatch.setenv("DECKY_CONFIG", str(tmp_path / "config.toml"))
    script = tmp_path / "reviewer.py"
    script.write_text(
        "import json, pathlib, sys\n"
        "prompt = sys.stdin.read()\n"
        "pathlib.Path(sys.argv[1]).write_text(prompt)\n"
        "print(sys.argv[2])\n"
    )
    settings = {"results_dir": str(tmp_path / "results"),
                "reviewer_command": [sys.executable, str(script), str(tmp_path / "primary"),
                                     json.dumps({"risk": "low", "summary": SUMMARY})],
                "second_reviewer_command": [sys.executable, str(script), str(tmp_path / "second"),
                                            json.dumps({"risk": "high", "summary": "Check access."})],
                "reviewer_label": "Configured primary", "second_reviewer_label": "Configured second"}
    row = {"head_sha": SHA, "draft": False, "title": "Add exports", "body": "Save reports",
           "files": [{"path": "reports.py", "additions": 3, "deletions": 1}]}
    monkeypatch.setattr(github, "load_pr", lambda *args: (row, []))
    monkeypatch.setattr(github, "run_gh", lambda *args: subprocess.CompletedProcess(args, 0, "+export\n", ""))
    latest = {"headRefOid": SHA, "isDraft": False}
    monkeypatch.setattr(github, "_gh_json", lambda *args: latest)

    def run(force=False):
        (tmp_path / "config.toml").write_text(tomli_w.dumps({"review": settings}))
        return CliRunner().invoke(cli, ["review-result", "write", "Example/Demo", "1", *(["--force"] if force else [])])

    return run, settings, row, latest


@pytest.mark.parametrize("flag", [None, "auth", "size", "extra", "truncated", "sending", "approval", "rewrite", "billing", "credentials", "migrations"])
def test_writes_valid_result_with_second_opinion_only_when_flagged(writer, tmp_path, flag):
    run, settings, row, _ = writer
    if flag in ("auth", "sending", "approval", "rewrite", "billing", "credentials", "migrations"):
        row["files"][0]["path"] = f"{ {'rewrite': 'data_rewrite'}.get(flag, flag) }/rules.py"
    elif flag == "size":
        settings["large_diff_lines"] = 4
    elif flag == "extra":
        settings["sensitive_patterns"] = ["reports"]
    elif flag == "truncated":
        settings["max_diff_bytes"] = 2
    result = run()
    assert result.exit_code == 0, result.output
    parsed = load(settings["results_dir"], "example/demo", 1, SHA)
    assert parsed["summary"] == SUMMARY and parsed["risk"] == "low" and not parsed["outdated"]
    assert parsed["reviewer"] == "Configured primary"
    assert bool(parsed["second_opinion"]) == bool(flag) == (tmp_path / "second").exists()
    if flag:
        assert parsed["second_opinion"] == {"reviewer": "Configured second", "risk": "high", "summary": "Check access."}
    prompt = (tmp_path / "primary").read_text()
    assert "untrusted data" in prompt
    if flag == "truncated":
        assert json.loads(prompt.split("\n", 1)[1])["diff"] == "+e"
    path = tmp_path / "results" / "example+demo-1.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert len(list(path.parent.iterdir())) == 1
    assert "Skipped" in run().output
    assert "Wrote" in run(force=True).output


@pytest.mark.parametrize("failure", ["json", "schema", "second", "missing_second", "changed_head", "draft", "unset", "exit", "timeout", "oversized"])
def test_failure_or_skip_writes_nothing(writer, tmp_path, failure):
    run, settings, row, latest = writer
    if failure in ("json", "schema"):
        settings["reviewer_command"][-1] = "broken" if failure == "json" else '{"risk":"critical"}'
    elif failure in ("second", "missing_second"):
        row["title"] = "Update auth"
        if failure == "second":
            settings["second_reviewer_command"][-1] = '{"risk":"high","summary":""}'
        else:
            settings["second_reviewer_command"] = []
    elif failure == "changed_head":
        latest["headRefOid"] = "b" * 40
    elif failure == "draft":
        row["draft"] = True
    elif failure in ("exit", "timeout", "oversized"):
        settings["reviewer_command"] = [sys.executable, "-c", {
            "exit": "raise SystemExit(2)", "timeout": "import time; time.sleep(2)",
            "oversized": "print('x' * 262145)",
        }[failure]]
        settings["reviewer_timeout"] = 1
    else:
        settings.pop("results_dir")
    result = run()
    assert result.exit_code == (0 if failure in ("draft", "unset") else 1), result.output
    assert not (tmp_path / "results").exists()
    if failure in ("draft", "unset", "missing_second"):
        assert not (tmp_path / "primary").exists()


def test_bad_regeneration_preserves_existing_result(writer, tmp_path):
    run, settings, _, _ = writer
    assert run().exit_code == 0
    path = tmp_path / "results" / "example+demo-1.json"
    original = path.read_bytes()
    settings["reviewer_command"][-1] = "broken"
    assert run(force=True).exit_code == 1
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


def test_ordinary_words_in_pr_body_and_diff_do_not_flag_small_change(writer, tmp_path, monkeypatch):
    run, settings, row, _ = writer
    row.update(title="Refresh author page favicon", body="Send for permission and approval.")
    row["files"][0]["path"] = "web/author/favicon.svg"
    monkeypatch.setattr(github, "run_gh", lambda *args: subprocess.CompletedProcess(
        args, 0, '+<svg aria-label="send permission"/>\n', ""))
    result = run()
    assert result.exit_code == 0, result.output
    assert load(settings["results_dir"], "example/demo", 1, SHA)["second_opinion"] is None
    assert not (tmp_path / "second").exists()

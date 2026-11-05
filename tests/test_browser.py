"""open_http_url."""

from __future__ import annotations

import pytest

from decky import browser


def test_rejects_non_http(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(Exception) as exc:
        browser.open_http_url("file:///etc/passwd")
    assert "http" in str(exc.value).lower()


def test_substitutes_url(monkeypatch: pytest.MonkeyPatch) -> None:
    runs: list[list[str]] = []
    monkeypatch.setattr(
        browser.config,
        "resolve",
        lambda key: ("open -a Dia {url}", "file") if key == "browser.command" else (None, "unset"),
    )
    monkeypatch.setattr(browser.subprocess, "run", lambda argv, **k: runs.append(argv))
    browser.open_http_url("http://127.0.0.1:4387/session/ab")
    assert runs == [["open", "-a", "Dia", "http://127.0.0.1:4387/session/ab"]]

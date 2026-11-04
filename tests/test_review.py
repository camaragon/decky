"""review.command interpolation."""

from __future__ import annotations

from pathlib import Path

from decky.review import interpolate


def test_tokens() -> None:
    dest = Path("/tmp/prs/api")
    out = interpolate(
        "{slug} {owner} {repo} {number} {url} {cwd}",
        slug="o/api",
        number=42,
        dest=dest,
    )
    assert out == "o/api o api 42 https://github.com/o/api/pull/42 /tmp/prs/api"


def test_unknown_token_unchanged() -> None:
    assert interpolate("{foo}", slug="a/b", number=1, dest=Path(".")) == "{foo}"

"""Repository identity throughout the review workflow."""

from pathlib import Path

import click
import pytest

from decky.commands import pr as pr_cmd


@pytest.mark.parametrize("terminal", ["tmux", "cmux"])
def test_reviews_keep_repository_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, terminal: str
) -> None:
    settings = {
        "review.command": "review {slug} {cwd}",
        "pr.dir": str(tmp_path),
        "terminal": terminal,
    }
    monkeypatch.setattr(
        pr_cmd.config, "resolve", lambda key: (settings.get(key), "test")
    )
    backend_type = type(pr_cmd.get_backend(terminal))
    surfaces = {}
    focused = []
    checkouts = {}

    def focus(self, name, url):
        if name not in surfaces:
            return False
        focused.append((name, url))
        return True

    def open_surface(self, name, cwd, command, url):
        surfaces[name] = (cwd, command, url)

    def checkout(slug, dest):
        if dest in checkouts and checkouts[dest] != slug:
            raise click.ClickException("checkout identity mismatch")
        checkouts[dest] = slug

    monkeypatch.setattr(backend_type, "focus_existing", focus)
    monkeypatch.setattr(backend_type, "open", open_surface)
    monkeypatch.setattr(pr_cmd.github, "clone_or_reuse", checkout)
    # A legacy checkout is left alone, including when it belongs to another owner.
    legacy = tmp_path / "api"
    legacy.mkdir()
    (legacy / "keep").write_text("unchanged")

    pr_cmd.open_review("alpha/api", 1)
    pr_cmd.open_review("beta/api", 1)
    assert len(surfaces) == 2
    assert set(checkouts.values()) == {"alpha/api", "beta/api"}
    assert len(checkouts) == 2
    assert all(dest != legacy for dest in checkouts)
    assert (legacy / "keep").read_text() == "unchanged"

    pr_cmd.open_review("ALPHA/API", 1)
    assert len(surfaces) == 2
    assert len(focused) == 1
    name, url = focused[0]
    assert surfaces[name][2] == url == "https://github.com/alpha/api/pull/1"

    # Revalidate a checkout even if its review surface is already open.
    dest = next(dest for dest, slug in checkouts.items() if slug == "alpha/api")
    checkouts[dest] = "other/api"
    with pytest.raises(click.ClickException, match="identity mismatch"):
        pr_cmd.open_review("alpha/api", 1)
    assert len(focused) == 1


@pytest.mark.parametrize("terminal", ["tmux", "cmux"])
def test_legacy_surface_is_not_owner_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, terminal: str
) -> None:
    settings = {
        "review.command": "review {slug} {cwd}",
        "pr.dir": str(tmp_path),
        "terminal": terminal,
    }
    monkeypatch.setattr(
        pr_cmd.config, "resolve", lambda key: (settings.get(key), "test")
    )
    backend_type = type(pr_cmd.get_backend(terminal))
    # Legacy pr-<repo>-<number> surface for a repository named alpha__api.
    surfaces = {"pr-alpha__api-1": None}
    focused = []
    checkouts = []

    def focus(self, name, url):
        if name not in surfaces:
            return False
        focused.append(name)
        return True

    def open_surface(self, name, cwd, command, url):
        surfaces[name] = (cwd, url)

    monkeypatch.setattr(backend_type, "focus_existing", focus)
    monkeypatch.setattr(backend_type, "open", open_surface)
    monkeypatch.setattr(
        pr_cmd.github, "clone_or_reuse", lambda slug, dest: checkouts.append(dest)
    )

    pr_cmd.open_review("alpha/api", 1)
    assert focused == []
    assert len(surfaces) == 2
    [(cwd, url)] = [v for k, v in surfaces.items() if k != "pr-alpha__api-1"]
    assert url == "https://github.com/alpha/api/pull/1"
    assert checkouts == [cwd]
    assert cwd.parent == tmp_path
    assert cwd.name not in {"api", "alpha__api"}

"""`decky pr`: list and review pull requests."""

from __future__ import annotations

from pathlib import Path

import click

from decky import config, github, tui
from decky import review as review_tpl
from decky.terminal import get_backend

KINDS = ("review", "team", "mine")
EMPTY = {
    "review": "no review requests",
    "team": "no team review requests",
    "mine": "no open PRs by you",
}
TITLES = {
    "review": "review requests",
    "team": "team review requests",
    "mine": "your PRs",
}

PR_HEADER = ("PR", "REPO", "AUTHOR", "CHECKS", "APPROVALS", "TITLE")


def pr_url(slug: str, number: int) -> str:
    return f"https://github.com/{slug}/pull/{number}"


def open_pr_action(template_key: str, name_prefix: str, slug: str, number: int) -> None:
    command_template, _ = config.resolve(template_key)
    if not command_template:
        raise click.UsageError(f"set {template_key} (see decky config init)")
    slug = slug.lower()
    # GitHub owner and repository names cannot contain "+".
    identity = slug.replace("/", "+")
    name = f"{name_prefix}-{identity}-{number}"
    parent, _ = config.resolve("pr.dir")
    dest_root = Path(parent or ".").expanduser().resolve()
    terminal, _ = config.resolve("terminal")
    backend = get_backend(terminal or "tmux")
    url = pr_url(slug, number)
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / identity
    github.clone_or_reuse(slug, dest)
    if backend.focus_existing(name, url):
        click.echo(f"switched to open {name}")
        return
    command = review_tpl.interpolate(
        command_template, slug=slug, number=number, dest=dest
    )
    backend.open(name, dest, command, url)


def open_review(slug: str, number: int) -> None:
    open_pr_action("review.command", "pr", slug, number)


def hidden_authors() -> list[str]:
    value, _ = config.resolve("pr.hide_authors")
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).lower().removesuffix("[bot]") for v in value]
    return []


def author_hidden(author: str, hidden: list[str]) -> bool:
    login = author.lower().removesuffix("[bot]")
    return login in hidden


def filter_prs(prs: list[dict], show_all: bool) -> tuple[list[dict], int]:
    if show_all:
        return prs, 0
    hidden = hidden_authors()
    shown = [
        p
        for p in prs
        if p["checks"] == "pass"
        and not p["draft"]
        and not author_hidden(p["author"], hidden)
    ]
    return shown, len(prs) - len(shown)


def hidden_note(hidden: int) -> str:
    return f"{hidden} hidden (draft, not passing, or hidden author); --all shows them"


def pr_header(drafts: bool) -> tuple[str, ...]:
    if drafts:
        return PR_HEADER[:-1] + ("DRAFT",) + PR_HEADER[-1:]
    return PR_HEADER


def pr_cells(p: dict, drafts: bool) -> tuple[str, ...]:
    draft = ("yes" if p["draft"] else "no",) if drafts else ()
    return (
        f"#{p['number']}",
        p["repo"],
        p["author"],
        p["checks"],
        str(p["approvals"]),
        *draft,
        p["title"],
    )


def pr_rows(prs: list[dict], header: bool = False, drafts: bool = False) -> list[str]:
    cells = [pr_cells(p, drafts) for p in prs]
    if header and cells:
        cells.insert(0, pr_header(drafts))
    if not cells:
        return []
    widths = [max(len(row[i]) for row in cells) for i in range(len(cells[0]) - 1)]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths))
        + "  "
        + row[-1]
        for row in cells
    ]


def fetch_lists() -> tuple[dict[str, list[dict]], list[str]]:
    lists, notes = github.load_pr_lists()
    return lists, notes


@click.group()
def pr() -> None:
    """Pull request helpers."""


@pr.command()
@click.argument("repo")
@click.argument("number", type=int)
@config.option("work_org", "--org", help="GitHub owner when REPO has no owner.")
def review(repo: str, number: int, org: str | None) -> None:
    """Open or focus a review workspace for REPO NUMBER."""
    open_review(github.repo_slug(repo, org), number)


@pr.command(name="list")
@config.interactive_option(
    "Select a PR; Enter review, o opens the URL, tab cycles lists, a toggles --all."
)
@click.option(
    "-a",
    "--all",
    "show_all",
    is_flag=True,
    help="Show drafts, failing checks, and hidden authors.",
)
@click.option("-m", "--mine", is_flag=True, help="List PRs you opened.")
@click.option("-t", "--team", is_flag=True, help="List team review requests.")
def list_prs(
    interactive: bool | None,
    show_all: bool,
    mine: bool,
    team: bool,
) -> None:
    """List open pull requests (alias ls)."""
    if mine and team:
        raise click.UsageError("cannot use --mine and --team together")
    kind = "mine" if mine else "team" if team else "review"
    use_interactive = config.interactive(interactive)

    lists, truncation_notes = fetch_lists()
    if not use_interactive:
        prs, hidden = filter_prs(lists[kind], show_all)
        for note in truncation_notes:
            click.echo(note, err=True)
        if hidden:
            click.echo(hidden_note(hidden), err=True)
        if not prs:
            click.echo(EMPTY[kind])
            return
        for row in pr_rows(prs, header=True, drafts=show_all):
            click.echo(row)
        return

    fetched = lists
    index = 0
    while True:
        prs, hidden = filter_prs(fetched[kind], show_all)
        title = TITLES[kind]
        hint_parts = []
        if hidden:
            title += f" ({hidden} hidden)"
        for note in truncation_notes:
            hint_parts.append(note)
        following = KINDS[(KINDS.index(kind) + 1) % len(KINDS)]
        keys = f"tab {TITLES[following]}, a {'filter' if show_all else 'show all'}"
        if prs:
            rows = pr_rows(prs, drafts=show_all)
            hint = f"{title} · enter review, o open, {keys}, q quit"
            if hint_parts:
                hint += " · " + "; ".join(hint_parts)
            actions: tuple[str, ...] = ("open", "browse", "cycle", "all")
        else:
            rows = [EMPTY[kind]]
            hint = f"{title} · {keys}, q quit"
            actions = ("cycle", "all")

        chosen = tui.choose(rows, min(index, len(rows) - 1), hint=hint, actions=actions)
        if chosen is None:
            return
        action, index = chosen
        if action == "cycle":
            kind = following
            index = 0
            continue
        if action == "all":
            show_all = not show_all
            index = 0
            continue
        if action == "browse":
            click.launch(pr_url(prs[index]["repo"], prs[index]["number"]))
            continue
        if action == "open":
            open_review(prs[index]["repo"], prs[index]["number"])
            return


pr.add_command(review, name="r")
pr.add_command(list_prs, name="ls")

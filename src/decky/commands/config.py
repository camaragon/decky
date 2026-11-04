"""`decky config`: read and write ~/.config/decky/config.toml."""

from __future__ import annotations

import os
import subprocess
import tomllib

import click

from decky import config


@click.group()
def config_group() -> None:
    """Show or edit the config file."""


@config_group.command()
def path() -> None:
    """Print the config file path."""
    click.echo(config.config_path())


@config_group.command("list")
def list_settings() -> None:
    """List every setting, its value, and where it came from."""
    for key in sorted(config.SETTINGS):
        value, source = config.resolve(key)
        if value is None:
            click.echo(f"{key}\t<unset>\t{source}")
        else:
            click.echo(f"{key}\t{value}\t{source}")


@config_group.command()
@click.argument("key")
def get(key: str) -> None:
    """Print one setting."""
    try:
        config.setting(key)
    except click.BadParameter as e:
        raise click.ClickException(str(e)) from None
    value, _ = config.resolve(key)
    if value is None:
        raise click.ClickException(f"{key} is unset")
    if isinstance(value, list):
        click.echo(",".join(value))
    else:
        click.echo(value)


@config_group.command()
@click.argument("key")
@click.argument("value")
def set(key: str, value: str) -> None:
    """Set KEY to VALUE in the config file."""
    try:
        parsed = config.parse_set_value(key, value)
    except click.BadParameter as e:
        raise click.ClickException(str(e)) from None
    if config.set_value(key, parsed):
        click.echo(f"warning: {key} is overridden by {config.setting(key).env}", err=True)


@config_group.command()
@click.argument("key")
def unset(key: str) -> None:
    """Remove KEY from the config file."""
    try:
        config.unset_value(key)
    except click.BadParameter as e:
        raise click.ClickException(str(e)) from None


@config_group.command()
@click.option("--force", is_flag=True, help="Overwrite an existing config file.")
def init(force: bool) -> None:
    """Write a commented example config file."""
    path = config.config_path()
    if path.exists() and not force:
        raise click.ClickException(f"{path} already exists (use --force to overwrite)")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(config.INIT_TEMPLATE, encoding="utf-8")
    os.chmod(path, 0o600)
    click.echo(path)


@config_group.command()
def edit() -> None:
    """Open the config file in $EDITOR."""
    path = config.config_path()
    if not path.exists():
        ctx = click.get_current_context()
        ctx.invoke(init)
    editor = os.environ.get("EDITOR")
    if not editor:
        if not os.isatty(0):
            raise click.ClickException("EDITOR is not set and stdin is not a TTY")
        editor = "vi"
    subprocess.run([editor, str(path)], check=False)
    try:
        with path.open("rb") as f:
            tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise click.ClickException(f"invalid config file {path}: {e}") from None

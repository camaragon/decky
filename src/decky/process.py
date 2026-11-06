"""Translate configured command failures into user-facing errors."""

import shlex
import subprocess

import click


def split_command(command: str, setting: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError:
        raise click.ClickException(f"{setting}: invalid quoting; check the command") from None
    if not argv:
        raise click.ClickException(f"{setting}: command is empty; set an executable")
    return argv


def run_command(argv: list[str], setting: str, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, **kwargs)
    except OSError:
        raise click.ClickException(
            f"{setting}: cannot launch executable; check its path and execute permissions"
        ) from None
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"{setting}: command exited {e.returncode}") from None


def launch(command: str, setting: str) -> None:
    result = run_command(split_command(command, setting), setting, capture_output=True, check=False)
    if result.returncode != 0:
        raise click.ClickException(f"{setting}: command exited {result.returncode}; check the command")

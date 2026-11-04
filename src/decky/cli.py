"""Root command group for decky."""

from __future__ import annotations

import click

from decky.commands.config import config_group
from decky.commands.pr import pr


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Personal workflow CLI."""


cli.add_command(config_group)
cli.add_command(pr)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

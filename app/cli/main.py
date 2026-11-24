"""
Entry point for the admin CLI.

Run via ``uv run python -m app.cli.main <command>``, same invocation style
as the rest of this project (e.g. ``uvicorn app.main:app``) -- the project
isn't packaged, so this isn't an installed console script.
"""

import click

from app.cli.users import create_user, refresh_password


@click.group()
def cli() -> None:
    """Admin commands for chur."""


cli.add_command(create_user)
cli.add_command(refresh_password)


if __name__ == "__main__":
    cli()

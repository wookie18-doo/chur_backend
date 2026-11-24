"""User administration commands: ``create-user``, ``refresh-password``."""

import click
from sqlalchemy.exc import IntegrityError

from app.cli._async import run_async
from app.cli._db import cli_session
from app.services.email_sender import NoopEmailSender
from app.services.user_service import UserNotFoundError, UserService


@click.command("create-user")
@click.option("--email", required=True, prompt=True, help="Email for the new user.")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Password for the new user.",
)
@click.option("--first-name", default=None, help="User's first name.")
@click.option("--last-name", default=None, help="User's last name.")
@click.option("--phone", default=None, help="User's phone number.")
@click.option("--username", default=None, help="User's handle.")
@click.option(
    "--superuser", is_flag=True, default=False, help="Grant superuser rights."
)
@click.option(
    "--verified/--unverified",
    default=True,
    help=(
        "Mark the account verified immediately instead of emailing a "
        "verification link (default: verified -- there's no inbox to "
        "prove ownership of for a CLI-created account)."
    ),
)
@run_async
async def create_user(
    *,
    email: str,
    password: str,
    first_name: str | None,
    last_name: str | None,
    phone: str | None,
    username: str | None,
    superuser: bool,
    verified: bool,
) -> None:
    """Create a new user account."""
    async with cli_session() as session:
        user_service = UserService(session, NoopEmailSender())
        try:
            user = await user_service.register(
                email,
                password,
                phone=phone,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_superuser=superuser,
                is_verified=verified,
            )
        except IntegrityError as exc:
            raise click.ClickException(
                f"Could not create user: {email!r} (or its phone/username) is "
                "already taken."
            ) from exc

        click.echo(f"Created user {user.email} (id={user.id}).")


@click.command("refresh-password")
@click.option(
    "--email", required=True, prompt=True, help="Email of the user to update."
)
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="New password for the user.",
)
@run_async
async def refresh_password(email: str, password: str) -> None:
    """Set a new password for an existing user, bypassing the reset-token flow."""
    async with cli_session() as session:
        user_service = UserService(session, NoopEmailSender())
        try:
            user = await user_service.set_password(email, password)
        except UserNotFoundError as exc:
            raise click.ClickException(f"No user found with email {email!r}.") from exc

        click.echo(f"Password updated for {user.email} (id={user.id}).")

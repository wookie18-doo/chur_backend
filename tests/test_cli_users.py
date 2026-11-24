"""
Tests for the ``create-user``/``refresh-password`` admin CLI commands.

These run against the real test db through the CLI's own
:func:`~app.cli._db.cli_session` (its own engine, not the ``dbsession``
fixture's SAVEPOINT-scoped one -- a CLI invocation commits for real, same
as it would outside tests), so each test cleans up the user it created
instead of relying on a rollback. Depending on the session-scoped
``_engine`` fixture (unused otherwise) guarantees the schema exists even
if this file runs on its own, with no other test having pulled
``dbsession``/``client`` in first.
"""

import asyncio
import uuid

from click.testing import CliRunner
from sqlalchemy.ext.asyncio import AsyncEngine

from app.cli._db import cli_session
from app.cli.main import cli
from app.dal.user_query import UserQuery
from app.services.auth_service import verify_secret


async def _delete_user(email: str) -> None:
    async with cli_session() as session:
        user = await UserQuery(session).get_by_email(email)
        if user is not None:
            await session.delete(user)


async def test_create_user_cli_creates_verified_superuser(_engine: AsyncEngine) -> None:
    """``create-user --superuser`` creates an active, verified superuser."""
    email = f"cli-{uuid.uuid4().hex}@example.com"
    runner = CliRunner()

    try:
        result = await asyncio.to_thread(
            runner.invoke,
            cli,
            [
                "create-user",
                "--email",
                email,
                "--password",
                "correct horse battery staple",
                "--superuser",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Created user" in result.output

        async with cli_session() as session:
            user = await UserQuery(session).get_by_email(email)
            assert user is not None
            assert user.is_active is True
            assert user.is_superuser is True
            assert user.is_verified is True
            assert verify_secret("correct horse battery staple", user.hashed_password)
    finally:
        await _delete_user(email)


async def test_create_user_cli_rejects_duplicate_email(_engine: AsyncEngine) -> None:
    """A second ``create-user`` for the same email fails cleanly, not a traceback."""
    email = f"cli-{uuid.uuid4().hex}@example.com"
    runner = CliRunner()
    args = [
        "create-user",
        "--email",
        email,
        "--password",
        "correct horse battery staple",
    ]

    try:
        first = await asyncio.to_thread(runner.invoke, cli, args)
        assert first.exit_code == 0, first.output

        second = await asyncio.to_thread(runner.invoke, cli, args)
        assert second.exit_code != 0
        assert "already taken" in second.output
    finally:
        await _delete_user(email)


async def test_refresh_password_cli_updates_password(_engine: AsyncEngine) -> None:
    """``refresh-password`` overwrites an existing user's password."""
    email = f"cli-{uuid.uuid4().hex}@example.com"
    runner = CliRunner()

    try:
        created = await asyncio.to_thread(
            runner.invoke,
            cli,
            ["create-user", "--email", email, "--password", "original password one"],
        )
        assert created.exit_code == 0, created.output

        result = await asyncio.to_thread(
            runner.invoke,
            cli,
            [
                "refresh-password",
                "--email",
                email,
                "--password",
                "brand new password two",
            ],
        )
        assert result.exit_code == 0, result.output

        async with cli_session() as session:
            user = await UserQuery(session).get_by_email(email)
            assert user is not None
            assert verify_secret("brand new password two", user.hashed_password)
            assert not verify_secret("original password one", user.hashed_password)
    finally:
        await _delete_user(email)


async def test_refresh_password_cli_rejects_unknown_email(_engine: AsyncEngine) -> None:
    """``refresh-password`` fails cleanly for an email with no matching user."""
    runner = CliRunner()

    result = await asyncio.to_thread(
        runner.invoke,
        cli,
        [
            "refresh-password",
            "--email",
            "no-such-cli-user@example.com",
            "--password",
            "whatever password",
        ],
    )

    assert result.exit_code != 0
    assert "No user found" in result.output

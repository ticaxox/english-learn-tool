from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import create_engine, create_session_factory
from app.services.users import bootstrap_admin


class CliError(RuntimeError):
    """A safe, user-facing command error that never contains secret values."""


def _environment_value(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _required_text(label: str, environment_name: str) -> str:
    value = _environment_value(environment_name)
    if value is not None:
        return value
    if not sys.stdin.isatty():
        raise CliError(f"{environment_name} is required in non-interactive mode.")
    value = input(f"{label}: ").strip()
    if not value:
        raise CliError(f"{label} must not be blank.")
    return value


def _required_password() -> str:
    value = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if value:
        return value
    if not sys.stdin.isatty():
        raise CliError("BOOTSTRAP_ADMIN_PASSWORD is required in non-interactive mode.")
    password = getpass.getpass("Initial administrator password: ")
    confirmation = getpass.getpass("Confirm initial administrator password: ")
    if password != confirmation:
        raise CliError("The password confirmation does not match.")
    return password


async def _bootstrap(username: str, display_name: str, password: str) -> str:
    settings = get_settings()
    configuration_errors = settings.runtime_configuration_errors()
    if configuration_errors:
        raise CliError("Runtime configuration is invalid: " + ", ".join(configuration_errors))

    engine = create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            user = await bootstrap_admin(
                session,
                username=username,
                display_name=display_name,
                password=password,
            )
            return user.username
    finally:
        await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Administrative bootstrap commands for the English learning backend.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "bootstrap-admin",
        help="Create the initial administrator when no active administrator exists.",
        description=(
            "Create the initial administrator. Values are read from "
            "BOOTSTRAP_ADMIN_USERNAME, BOOTSTRAP_ADMIN_DISPLAY_NAME, and "
            "BOOTSTRAP_ADMIN_PASSWORD, or prompted without echoing the password."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command != "bootstrap-admin":
        parser.error("Unsupported command.")

    try:
        username = _required_text("Administrator username", "BOOTSTRAP_ADMIN_USERNAME")
        display_name = _required_text("Administrator display name", "BOOTSTRAP_ADMIN_DISPLAY_NAME")
        password = _required_password()
        created_username = asyncio.run(_bootstrap(username, display_name, password))
    except (AppError, CliError, ValueError) as exc:
        message = exc.message if isinstance(exc, AppError) else str(exc)
        print(f"Bootstrap failed: {message}", file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print(
            "Bootstrap failed: database access failed. Verify DATABASE_URL and run "
            "`uv run alembic upgrade head` first.",
            file=sys.stderr,
        )
        return 2

    print(f"Created initial administrator '{created_username}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

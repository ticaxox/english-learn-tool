from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import create_engine, create_session_factory
from app.services.users import bootstrap_admin
from app.services.wordbook_parser import (
    WordbookParseError,
    parse_wordbook_bytes,
    parse_wordbook_json_document,
)

WORDBOOK_CONVERTER_VERSION = "english-learn-wordbook-converter/1.0.0"


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


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary_path.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _convert_wordbook(
    input_path: Path,
    output_path: Path,
    report_path: Path | None,
) -> tuple[int, int, int]:
    raw = input_path.read_bytes()
    report: dict[str, Any] = {
        "converter_version": WORDBOOK_CONVERTER_VERSION,
        "source_filename": input_path.name,
    }
    try:
        parsed = parse_wordbook_bytes(raw, input_path.name)
    except WordbookParseError as exc:
        report.update(
            {
                "status": "failed",
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            }
        )
        if report_path is not None:
            _atomic_write(
                report_path,
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
        raise CliError(f"{exc.code}: {exc.message}") from exc

    document = {
        **parse_wordbook_json_document(parsed),
        "converter_version": WORDBOOK_CONVERTER_VERSION,
    }
    report.update(
        {
            "status": "completed" if parsed.error_count == 0 else "completed_with_errors",
            "detected_format": parsed.detected_format,
            "encoding": parsed.encoding,
            "delimiter": parsed.delimiter,
            "total_rows": parsed.total_rows,
            "valid_entries": len(parsed.entries),
            "error_count": parsed.error_count,
            "warning_count": parsed.warning_count,
            "errors": parsed.errors,
            "warnings": parsed.warnings,
        }
    )
    _atomic_write(
        output_path,
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    if report_path is not None:
        _atomic_write(
            report_path,
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    return len(parsed.entries), parsed.warning_count, parsed.error_count


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
    convert_parser = subcommands.add_parser(
        "convert-wordbook",
        help="Convert a supported import file to deterministic wordbook JSON.",
        description=(
            "Run the production normalizer, duplicate merger, and validation rules, then "
            f"write deterministic JSON using {WORDBOOK_CONVERTER_VERSION}."
        ),
    )
    convert_parser.add_argument("input", type=Path, help="Approved CSV, JSON, or TXT source.")
    convert_parser.add_argument("output", type=Path, help="Destination canonical JSON file.")
    convert_parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report containing warnings and rejected rows.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "convert-wordbook":
        try:
            valid, warnings, errors = _convert_wordbook(
                arguments.input,
                arguments.output,
                arguments.report,
            )
        except (CliError, OSError) as exc:
            print(f"Conversion failed: {exc}", file=sys.stderr)
            return 2
        print(
            f"Converted {valid} entries with {warnings} warnings and {errors} rejected rows "
            f"to {arguments.output}."
        )
        return 0 if errors == 0 else 2

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

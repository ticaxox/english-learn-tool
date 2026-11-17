import asyncio
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy import select

from app.core.config import Settings
from app.models.wordbooks import WordbookImportPreview
from app.services.wordbook_exports import (
    ExportDefinition,
    ExportEntry,
    ExportExample,
    render_wordbook_export,
)
from app.services.wordbook_jobs import process_wordbook_job
from app.services.wordbook_parser import WordbookParseError, parse_wordbook_bytes
from tests.learning_support import seed_wordbook

LOGIN_PATH = "/api/v1/auth/login"
WORDBOOKS_PATH = "/api/v1/wordbooks"
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _csv_payload(
    rows: list[list[str]],
    *,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> bytes:
    columns = [
        "headword",
        "phonetic",
        "part_of_speech",
        "definition_en",
        "definition_zh",
        "example",
        "example_translation",
    ]
    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue().encode(encoding)


def _minimal_row(headword: str = "harbor") -> list[str]:
    return [
        headword,
        "ˈhɑːrbər",
        "n.",
        "a place where ships stop",
        "港口",
        "The ship entered the harbor.",
        "船驶入港口。",
    ]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _read_wordbook_artifact_in_worker_process(
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    read_code = (
        "import asyncio, hashlib, os; "
        "from app.services.wordbook_storage import LocalFileStorage; "
        "storage=LocalFileStorage(os.environ['WORDBOOK_STORAGE_DIR']); "
        "data=asyncio.run(storage.read_bytes(os.environ['WORDBOOK_KEY'])); "
        "print(hashlib.sha256(data).hexdigest())"
    )
    return subprocess.run(
        [sys.executable, "-c", read_code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


async def _login_headers(client: httpx.AsyncClient, username: str) -> dict[str, str]:
    response = await client.post(
        LOGIN_PATH,
        json={"username": username, "password": "Valid-Test-Pass-123!"},
    )
    assert response.status_code == 200
    return _bearer(response.json()["access_token"])


async def _process_job(app, job_id: str) -> dict:
    return await process_wordbook_job(
        {
            "session_factory": app.state.session_factory,
            "settings": app.state.settings,
            "wordbook_storage": app.state.wordbook_storage,
        },
        job_id,
    )


def test_wordbook_storage_must_be_absolute_and_cross_process_readable(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(wordbook_storage_dir="./var/wordbooks")

    shared_root = tmp_path / "shared-wordbooks"
    shared_root.mkdir()
    env = os.environ.copy()
    env["WORDBOOK_STORAGE_DIR"] = str(shared_root)
    backend_dir = Path(__file__).resolve().parents[1]
    write_code = (
        "import asyncio, os; "
        "from app.services.wordbook_storage import LocalFileStorage; "
        "storage=LocalFileStorage(os.environ['WORDBOOK_STORAGE_DIR']); "
        "print(asyncio.run(storage.save_bytes(b'shared-artifact', "
        "extension='txt', prefix='preview')))"
    )
    written = subprocess.run(
        [sys.executable, "-c", write_code],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    key = written.stdout.strip()
    assert key.startswith("preview-")

    read_code = (
        "import asyncio, os; "
        "from app.services.wordbook_storage import LocalFileStorage; "
        "storage=LocalFileStorage(os.environ['WORDBOOK_STORAGE_DIR']); "
        "print(asyncio.run(storage.read_bytes(os.environ['WORDBOOK_KEY'])).decode())"
    )
    read_env = {**env, "WORDBOOK_KEY": key}
    read = subprocess.run(
        [sys.executable, "-c", read_code],
        cwd=backend_dir,
        env=read_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert read.stdout.strip() == "shared-artifact"


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-8", "gb18030", "utf-16-le", "utf-16-be"])
@pytest.mark.parametrize("delimiter", [",", "\t", ";", "|"])
def test_parser_supports_csv_encodings_and_delimiters(encoding: str, delimiter: str) -> None:
    raw = _csv_payload(
        [_minimal_row()],
        delimiter=delimiter,
        encoding=encoding,
    )
    result = parse_wordbook_bytes(raw, "words.csv")

    assert result.detected_format == "csv"
    assert result.encoding == encoding
    assert result.delimiter == delimiter
    assert result.valid_rows == 1
    assert result.entries[0].normalized_headword == "harbor"


def test_parser_normalizes_and_merges_duplicate_spellings_and_examples() -> None:
    raw = _csv_payload(
        [
            ["  ＡＢＣ  ", "eɪ", "n.", "first", "第一", "Example one", "例句一"],
            ["abc", "eɪ", "n.", "first", "第一", "Example two", "例句二"],
            ["abc", "eɪ", "n.", "second", "第二", "", ""],
        ]
    )
    result = parse_wordbook_bytes(raw, "words.csv")

    assert result.valid_rows == 1
    assert result.warning_count == 2
    assert result.entries[0].headword == "ＡＢＣ"
    assert result.entries[0].normalized_headword == "abc"
    assert len(result.entries[0].definitions) == 2
    assert len(result.entries[0].definitions[0].examples) == 2


def test_parser_supports_both_json_shapes_and_rejects_bad_txt_lines() -> None:
    row = {
        "headword": "harbor",
        "phonetic": "ˈhɑːrbər",
        "definition_en": "a place where ships stop",
        "definition_zh": "港口",
    }
    for payload in ([row], {"words": [row]}):
        result = parse_wordbook_bytes(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "words.json",
        )
        assert result.detected_format == "json"
        assert result.valid_rows == 1
        assert result.entries[0].headword == "harbor"

    invalid = parse_wordbook_bytes(b"onlyoneword\n", "words.txt")
    assert invalid.detected_format == "txt"
    assert invalid.valid_rows == 0
    assert invalid.error_count == 1
    assert invalid.errors[0]["code"] == "TXT_LINE_UNRELIABLE"


def test_parser_enforces_file_and_logical_entry_boundaries() -> None:
    limit = 10 * 1024 * 1024
    base = _csv_payload([_minimal_row()])
    padded = base + b"\n" + b" " * (limit - len(base) - 1)
    assert len(padded) == limit
    assert parse_wordbook_bytes(padded, "words.csv", max_bytes=limit).valid_rows == 1

    with pytest.raises(WordbookParseError, match="permitted size"):
        parse_wordbook_bytes(padded + b" ", "words.csv", max_bytes=limit)

    rows = [(_minimal_row(f"word-{index}")) for index in range(20_000)]
    twenty_thousand = _csv_payload(rows)
    assert parse_wordbook_bytes(twenty_thousand, "words.csv").valid_rows == 20_000
    with pytest.raises(WordbookParseError, match="too many logical entries"):
        parse_wordbook_bytes(
            _csv_payload(rows + [_minimal_row("word-20000")]),
            "words.csv",
        )


def test_csv_export_neutralizes_spreadsheet_formulas_and_pdf_preserves_cjk_and_ipa() -> None:
    entry = ExportEntry(
        headword="café",
        phonetic="kæˈfeɪ",
        definitions=(
            ExportDefinition(
                part_of_speech="n.",
                definition_en="=SUM(1,1)",
                definition_zh="咖啡",
                examples=(ExportExample(example_en="+cmd", example_zh="@公式"),),
            ),
        ),
    )
    negative_entry = ExportEntry(
        headword="-2+3",
        phonetic="minus",
        definitions=(
            ExportDefinition(
                part_of_speech="n.",
                definition_en="safe",
                definition_zh="安全",
                examples=(),
            ),
        ),
    )
    csv_content = render_wordbook_export(
        (entry, negative_entry),
        export_format="csv",
        page_rows=18,
        columns=2,
    ).decode("utf-8-sig")
    csv_rows = list(csv.reader(io.StringIO(csv_content)))
    assert csv_rows[1][3] == "'=SUM(1,1)"
    assert csv_rows[1][5] == "'+cmd"
    assert csv_rows[1][6] == "'@公式"
    assert csv_rows[2][0] == "'-2+3"

    pdf_content = render_wordbook_export(
        (entry,),
        export_format="pdf",
        page_rows=18,
        columns=2,
    )
    text = PdfReader(io.BytesIO(pdf_content)).pages[0].extract_text()
    assert "咖啡" in text
    assert "kæˈfeɪ" in text
    assert "=SUM(1,1)" in text


async def test_api_preview_is_readable_from_a_separate_worker_process(
    client: httpx.AsyncClient,
    app,
    admin_user,
) -> None:
    headers = await _login_headers(client, admin_user.username)
    response = await client.post(
        f"{WORDBOOKS_PATH}/import/preview",
        headers=headers,
        data={"visibility": "private", "name": "Cross-process preview"},
        files={"file": ("words.csv", _csv_payload([_minimal_row()]), "text/csv")},
    )
    assert response.status_code == 201, response.text
    preview_id = UUID(response.json()["preview_id"])

    async with app.state.session_factory() as session:
        preview = await session.scalar(
            select(WordbookImportPreview).where(WordbookImportPreview.id == preview_id)
        )
    assert preview is not None

    env = os.environ.copy()
    env["WORDBOOK_STORAGE_DIR"] = str(Path(env["WORDBOOK_STORAGE_DIR"]))
    env["WORDBOOK_KEY"] = preview.storage_key
    worker_read = await asyncio.to_thread(_read_wordbook_artifact_in_worker_process, env)
    expected_hash = hashlib.sha256(_csv_payload([_minimal_row()])).hexdigest()
    assert worker_read.stdout.strip() == expected_hash


async def test_cors_preflight_allows_idempotency_key(client: httpx.AsyncClient) -> None:
    response = await client.options(
        f"{WORDBOOKS_PATH}/import/preview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )

    assert response.status_code == 200
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()


async def test_wordbook_shelf_shows_own_and_builtin_books_and_guards_the_rest(
    client, app, admin_user, member_user, user_factory
) -> None:
    owner_headers = await _login_headers(client, member_user.username)
    other_user = await user_factory(role="member")
    other_headers = await _login_headers(client, other_user.username)
    admin_headers = await _login_headers(client, admin_user.username)

    owner_book = await seed_wordbook(app, owner_id=member_user.id, entries=2)
    other_book = await seed_wordbook(app, owner_id=other_user.id, entries=2)
    legacy_organization = await seed_wordbook(
        app, owner_id=member_user.id, entries=2, visibility="organization"
    )

    owner_list = await client.get(WORDBOOKS_PATH, headers=owner_headers)
    visible = {item["id"]: item for item in owner_list.json()["items"]}
    # The shelf is the learner's own books plus the built-in ones.
    assert owner_book in visible
    assert legacy_organization in visible
    assert visible[legacy_organization]["is_builtin"] is True
    assert visible[owner_book]["is_builtin"] is False
    # Another learner's private book stays theirs.
    assert other_book not in owner_list.text

    owner_detail = await client.get(f"{WORDBOOKS_PATH}/{owner_book}", headers=owner_headers)
    assert owner_detail.status_code == 200
    assert owner_detail.json()["wordbook"]["visibility"] == "private"

    denied = [
        await client.get(f"{WORDBOOKS_PATH}/{owner_book}", headers=other_headers),
        await client.get(f"{WORDBOOKS_PATH}/{owner_book}", headers=admin_headers),
        await client.post(f"{WORDBOOKS_PATH}/{owner_book}/activate", headers=other_headers),
        await client.post(f"{WORDBOOKS_PATH}/{owner_book}/activate", headers=admin_headers),
        await client.post(
            f"{WORDBOOKS_PATH}/{legacy_organization}/export",
            headers={**other_headers, "Idempotency-Key": "builtin-export-1"},
            json={"format": "csv"},
        ),
        await client.request(
            "DELETE",
            f"{WORDBOOKS_PATH}/{legacy_organization}",
            headers={**other_headers, "Idempotency-Key": "builtin-delete-1"},
            json={},
        ),
        await client.post(
            f"{WORDBOOKS_PATH}/{owner_book}/export",
            headers={**other_headers, "Idempotency-Key": "foreign-export-1"},
            json={"format": "csv"},
        ),
        await client.request(
            "DELETE",
            f"{WORDBOOKS_PATH}/{owner_book}",
            headers={**other_headers, "Idempotency-Key": "foreign-delete-1"},
            json={},
        ),
    ]
    for response in denied:
        assert response.status_code == 404
        assert response.json()["code"] == "WORDBOOK_NOT_FOUND"

    # The built-in shelf is reachable, and readable, by everyone.
    builtin_detail = await client.get(
        f"{WORDBOOKS_PATH}/{legacy_organization}", headers=other_headers
    )
    assert builtin_detail.status_code == 200
    assert builtin_detail.json()["wordbook"]["is_builtin"] is True

    # Publishing is an administrator's act; a member is turned away.
    member_organization_import = await client.post(
        f"{WORDBOOKS_PATH}/import/preview",
        headers=owner_headers,
        data={"visibility": "organization", "name": "Member shared book"},
        files={"file": ("words.csv", _csv_payload([_minimal_row()]), "text/csv")},
    )
    assert member_organization_import.status_code == 403
    assert member_organization_import.json()["code"] == "WORDBOOK_BUILTIN_FORBIDDEN"

    organization_import = await client.post(
        f"{WORDBOOKS_PATH}/import/preview",
        headers=admin_headers,
        data={"visibility": "organization", "name": "Built-in book"},
        files={"file": ("words.csv", _csv_payload([_minimal_row()]), "text/csv")},
    )
    assert organization_import.status_code == 201

    activated = await client.post(f"{WORDBOOKS_PATH}/{owner_book}/activate", headers=owner_headers)
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True


@pytest.mark.parametrize("file_format", ["csv", "json", "txt"])
async def test_private_wordbook_api_lifecycle_uses_durable_worker_jobs(
    client: httpx.AsyncClient,
    app,
    admin_user,
    file_format: str,
) -> None:
    headers = await _login_headers(client, admin_user.username)
    headword = f"harbor-{file_format}"
    if file_format == "csv":
        filename = "words.csv"
        content_type = "text/csv"
        content = _csv_payload([_minimal_row(headword)])
    elif file_format == "json":
        filename = "words.json"
        content_type = "application/json"
        content = json.dumps(
            [
                {
                    "headword": headword,
                    "phonetic": "ˈhɑːrbər",
                    "part_of_speech": "n.",
                    "definition_en": [
                        "a place where ships stop",
                        "a sheltered area for boats",
                    ],
                    "definition_zh": ["港口", "避风港"],
                    "example": ["The ship entered the harbor.", "The boats waited in the harbor."],
                    "example_translation": ["船驶入港口。", "船只停在港内。"],
                }
            ],
            ensure_ascii=False,
        ).encode("utf-8")
    else:
        filename = "words.txt"
        content_type = "text/plain"
        content = ("\t".join(_minimal_row(headword)) + "\n").encode("utf-8")

    preview_response = await client.post(
        f"{WORDBOOKS_PATH}/import/preview",
        headers=headers,
        data={"visibility": "private", "name": f"{file_format} API lifecycle book"},
        files={"file": (filename, content, content_type)},
    )
    assert preview_response.status_code == 201, preview_response.text
    preview = preview_response.json()
    assert preview["detected_format"] == file_format
    assert preview["error_count"] == 0
    assert preview["valid_rows"] == 1

    remap_response = await client.patch(
        f"{WORDBOOKS_PATH}/import/previews/{preview['preview_id']}",
        headers=headers,
        json={
            "preview_token": preview["preview_token"],
            "mapping": preview["mapping"],
            "ignored_columns": preview["ignored_columns"],
        },
    )
    assert remap_response.status_code == 200, remap_response.text
    preview = remap_response.json()
    assert preview["detected_format"] == file_format
    assert preview["status"] == "previewed"

    confirm_response = await client.post(
        f"{WORDBOOKS_PATH}/import",
        headers={**headers, "Idempotency-Key": "wordbook-import-api-1"},
        json={
            "preview_id": preview["preview_id"],
            "preview_token": preview["preview_token"],
            "preview_hash": preview["preview_hash"],
            "name": preview["requested_name"],
            "visibility": "private",
        },
    )
    assert confirm_response.status_code == 202, confirm_response.text
    import_job = confirm_response.json()
    assert import_job["status"] == "queued"
    import_result = await _process_job(app, import_job["job_id"])
    assert import_result["entry_count"] == 1

    import_poll = await client.get(
        f"{WORDBOOKS_PATH}/jobs/{import_job['job_id']}",
        headers=headers,
    )
    assert import_poll.status_code == 200
    assert import_poll.json()["status"] == "succeeded"
    wordbook_id = import_poll.json()["wordbook_id"]

    detail = await client.get(f"{WORDBOOKS_PATH}/{wordbook_id}", headers=headers)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["entries"][0]["headword"] == headword
    if file_format == "json":
        definitions = detail_body["entries"][0]["definitions"]
        assert len(definitions) == 2
        assert all(len(definition["examples"]) == 2 for definition in definitions)
        assert {definition["examples"][0]["example_en"] for definition in definitions} == {
            "The ship entered the harbor."
        }

    activation = await client.post(f"{WORDBOOKS_PATH}/{wordbook_id}/activate", headers=headers)
    assert activation.status_code == 200
    assert activation.json()["is_active"] is True

    export_response = await client.post(
        f"{WORDBOOKS_PATH}/{wordbook_id}/export",
        headers={**headers, "Idempotency-Key": "wordbook-export-api-1"},
        json={"format": "csv"},
    )
    assert export_response.status_code == 202, export_response.text
    export_job = export_response.json()
    export_result = await _process_job(app, export_job["job_id"])
    assert export_result["entry_count"] == 1
    export_poll = await client.get(
        f"/api/v1/exports/{export_job['job_id']}",
        headers=headers,
    )
    assert export_poll.status_code == 200
    assert export_poll.json()["download_url"]

    downloaded = await client.get(export_poll.json()["download_url"], headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("text/csv")
    assert downloaded.content.startswith(b"\xef\xbb\xbfheadword,")

    delete_response = await client.request(
        "DELETE",
        f"{WORDBOOKS_PATH}/{wordbook_id}",
        headers={**headers, "Idempotency-Key": "wordbook-delete-api-1"},
        json={},
    )
    assert delete_response.status_code == 202, delete_response.text
    delete_job = delete_response.json()
    delete_result = await _process_job(app, delete_job["job_id"])
    assert delete_result["deleted_entries"] == 1
    assert (await client.get(f"{WORDBOOKS_PATH}/{wordbook_id}", headers=headers)).status_code == 404

    delete_poll = await client.get(
        f"{WORDBOOKS_PATH}/jobs/{delete_job['job_id']}",
        headers=headers,
    )
    assert delete_poll.status_code == 200
    assert delete_poll.json()["status"] == "succeeded"
    assert delete_poll.json()["cleanup_status"] == "completed"

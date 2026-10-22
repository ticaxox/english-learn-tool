from __future__ import annotations

import csv
import io
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_FORMATS = ("csv", "json", "txt")
SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "utf-16-le", "utf-16-be")
CSV_DELIMITERS = (",", "\t", ";", "|")

CANONICAL_FIELDS = (
    "headword",
    "phonetic",
    "part_of_speech",
    "definition_en",
    "definition_zh",
    "example",
    "example_translation",
)

_ALIASES = {
    "headword": {"headword", "word", "spelling", "term", "单词", "词条", "词"},
    "phonetic": {"phonetic", "ipa", "pronunciation", "音标"},
    "part_of_speech": {"part_of_speech", "pos", "partofspeech", "词性"},
    "definition_en": {
        "definition",
        "definition_en",
        "english_definition",
        "meaning",
        "meaning_en",
        "英文释义",
        "释义",
    },
    "definition_zh": {
        "definition_zh",
        "chinese_definition",
        "meaning_zh",
        "中文释义",
    },
    "example": {"example", "example_en", "sentence", "例句"},
    "example_translation": {
        "example_translation",
        "example_zh",
        "translation",
        "例句翻译",
    },
}


class WordbookParseError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class ParsedExample:
    example_en: str
    example_zh: str | None = None


@dataclass
class ParsedDefinition:
    part_of_speech: str | None
    definition_en: str
    definition_zh: str
    examples: list[ParsedExample] = field(default_factory=list)


@dataclass
class ParsedEntry:
    headword: str
    normalized_headword: str
    phonetic: str | None
    definitions: list[ParsedDefinition] = field(default_factory=list)


@dataclass
class ParseResult:
    detected_format: str
    encoding: str
    delimiter: str | None
    columns: list[str]
    suggested_mapping: dict[str, str | None]
    mapping: dict[str, str | None]
    ignored_columns: list[str]
    entries: list[ParsedEntry]
    sample_rows: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    total_rows: int
    valid_rows: int
    warning_count: int
    error_count: int

    def canonical_entries(self) -> list[dict[str, Any]]:
        return [
            {
                "headword": entry.headword,
                "phonetic": entry.phonetic,
                "definitions": [
                    {
                        "part_of_speech": definition.part_of_speech,
                        "definition_en": definition.definition_en,
                        "definition_zh": definition.definition_zh,
                        "examples": [
                            {
                                "example_en": example.example_en,
                                "example_zh": example.example_zh,
                            }
                            for example in definition.examples
                        ],
                    }
                    for definition in entry.definitions
                ],
            }
            for entry in self.entries
        ]


def normalize_headword(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _dedupe_names(names: list[str]) -> list[str]:
    seen: Counter[str] = Counter()
    result: list[str] = []
    for index, raw_name in enumerate(names, start=1):
        name = raw_name.strip() or f"column_{index}"
        count = seen[name] + 1
        seen[name] = count
        result.append(name if count == 1 else f"{name}_{count}")
    return result


def _decode(raw: bytes) -> tuple[str, str]:
    if not raw:
        raise WordbookParseError("IMPORT_FILE_EMPTY", "The uploaded file is empty.")

    has_utf16_bom = raw.startswith((b"\xff\xfe", b"\xfe\xff"))
    has_nul = b"\x00" in raw
    for encoding in SUPPORTED_ENCODINGS:
        if encoding.startswith("utf-16") and not (has_utf16_bom or has_nul):
            continue
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        text = text.removeprefix("\ufeff")
        if "\x00" in text:
            continue
        return text, encoding
    raise WordbookParseError(
        "IMPORT_ENCODING_UNRECOGNIZED",
        "The file encoding could not be recognized.",
        details={"attempted": list(SUPPORTED_ENCODINGS)},
    )


def _json_rows(text: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WordbookParseError(
            "IMPORT_JSON_INVALID",
            "The JSON file is not valid JSON.",
            details={"line": exc.lineno, "column": exc.colno},
        ) from exc
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict) and isinstance(value.get("words"), list):
        rows = value["words"]
    else:
        raise WordbookParseError(
            "IMPORT_JSON_SHAPE_INVALID",
            "JSON must be a top-level array or an object containing a words array.",
        )
    invalid_rows = [index + 1 for index, row in enumerate(rows) if not isinstance(row, dict)]
    if invalid_rows:
        raise WordbookParseError(
            "IMPORT_JSON_ROW_INVALID",
            "Every JSON word entry must be an object.",
            details={"rows": invalid_rows[:20]},
        )
    return rows


def _csv_rows(text: str) -> tuple[list[list[str]], str]:
    best: tuple[tuple[int, int, int], list[list[str]], str] | None = None
    for delimiter in CSV_DELIMITERS:
        try:
            reader = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        except csv.Error:
            continue
        rows = [row for row in reader if any(cell.strip() for cell in row)]
        if not rows or not rows[0]:
            continue
        widths = [len(row) for row in rows if row]
        if not widths:
            continue
        mode_width, frequency = Counter(widths).most_common(1)[0]
        score = (int(frequency / len(widths) * 100), mode_width, frequency)
        if mode_width > 1 and (best is None or score > best[0]):
            best = (score, rows, delimiter)
    if best is None:
        raise WordbookParseError(
            "IMPORT_DELIMITER_UNRECOGNIZED",
            "A stable CSV delimiter could not be detected.",
        )
    return best[1], best[2]


def _suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    normalized = {
        "".join(ch for ch in column.casefold().strip() if ch.isalnum() or ch in "_-"): column
        for column in columns
    }
    result: dict[str, str | None] = {}
    for canonical in CANONICAL_FIELDS:
        result[canonical] = next(
            (normalized[alias] for alias in _ALIASES[canonical] if alias in normalized),
            None,
        )
    return result


def _resolve_mapping(
    columns: list[str],
    *,
    suggested: dict[str, str | None],
    mapping: dict[str, str | None] | None,
    ignored_columns: list[str] | None,
) -> dict[str, str | None]:
    ignored = ignored_columns or []
    unknown = set(ignored) - set(columns)
    if unknown:
        raise WordbookParseError(
            "IMPORT_MAPPING_INVALID",
            "Ignored columns must refer to detected columns.",
            details={"unknown": sorted(unknown)},
        )
    resolved = dict(suggested)
    if mapping is not None:
        unknown_fields = set(mapping) - set(CANONICAL_FIELDS)
        if unknown_fields:
            raise WordbookParseError(
                "IMPORT_MAPPING_INVALID",
                "The mapping contains unknown fields.",
                details={"unknown_fields": sorted(unknown_fields)},
            )
        for field_name, source in mapping.items():
            if source is not None and source not in columns:
                raise WordbookParseError(
                    "IMPORT_MAPPING_INVALID",
                    "A mapped source column does not exist.",
                    details={"field": field_name, "source": source},
                )
            resolved[field_name] = source

    used_sources = [source for source in resolved.values() if source is not None]
    duplicates = [source for source, count in Counter(used_sources).items() if count > 1]
    if duplicates:
        raise WordbookParseError(
            "IMPORT_MAPPING_INVALID",
            "A source column cannot be mapped to multiple fields.",
            details={"duplicate_sources": sorted(duplicates)},
        )
    for field_name in ("headword", "definition_en", "definition_zh"):
        source = resolved.get(field_name)
        if source in ignored:
            resolved[field_name] = None
    return resolved


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        values = [_clean(item) for item in value]
        return [item for item in values if item]
    cleaned = _clean(value)
    return [cleaned] if cleaned else []


def _row_value(row: dict[str, Any], source: str | None) -> Any:
    return row.get(source, "") if source else ""


def _parse_structured_rows(
    rows: list[dict[str, Any]],
    *,
    columns: list[str],
    mapping: dict[str, str | None],
    result_builder: _ResultBuilder,
) -> None:
    result_builder.columns = columns
    for line_number, row in enumerate(rows, start=1):
        result_builder.total_rows += 1
        if not any(_clean(value) for value in row.values()):
            result_builder.errors.append(
                {
                    "line_number": line_number,
                    "code": "IMPORT_ROW_EMPTY",
                    "message": "The row is empty.",
                }
            )
            continue

        raw_headword = _row_value(row, mapping.get("headword"))
        headword = _clean(raw_headword)
        normalized = normalize_headword(headword)
        en_values = _values(_row_value(row, mapping.get("definition_en")))
        zh_values = _values(_row_value(row, mapping.get("definition_zh")))
        phonetic = _clean(_row_value(row, mapping.get("phonetic"))) or None
        part_of_speech = _clean(_row_value(row, mapping.get("part_of_speech"))) or None
        example_values = _values(_row_value(row, mapping.get("example")))
        example_zh_values = _values(_row_value(row, mapping.get("example_translation")))

        errors: list[str] = []
        if not headword:
            errors.append("HEADWORD_REQUIRED")
        elif len(headword) > 200:
            errors.append("HEADWORD_TOO_LONG")
        if not en_values:
            errors.append("DEFINITION_EN_REQUIRED")
        if not zh_values:
            errors.append("DEFINITION_ZH_REQUIRED")
        if en_values and zh_values and len(en_values) != len(zh_values):
            errors.append("DEFINITION_PAIRING_INVALID")
        if example_zh_values and not example_values:
            errors.append("EXAMPLE_EN_REQUIRED")
        if example_values and example_zh_values and len(example_values) != len(example_zh_values):
            errors.append("EXAMPLE_PAIRING_INVALID")
        if phonetic and len(phonetic) > 200:
            errors.append("PHONETIC_TOO_LONG")
        if part_of_speech and len(part_of_speech) > 64:
            errors.append("PART_OF_SPEECH_TOO_LONG")

        if errors:
            for code in errors:
                result_builder.errors.append(
                    {
                        "line_number": line_number,
                        "code": code,
                        "message": _ERROR_MESSAGES.get(code, code),
                    }
                )
            continue

        definitions: list[ParsedDefinition] = []
        for definition_en_value, definition_zh_value in zip(en_values, zh_values, strict=True):
            examples: list[ParsedExample] = []
            if example_values:
                examples = [
                    ParsedExample(example_en, example_zh)
                    for example_en, example_zh in zip(
                        example_values,
                        example_zh_values or [None] * len(example_values),
                        strict=True,
                    )
                ]
            definitions.append(
                ParsedDefinition(
                    part_of_speech=part_of_speech,
                    definition_en=definition_en_value,
                    definition_zh=definition_zh_value,
                    examples=examples,
                )
            )
        result_builder.add_entry(
            ParsedEntry(
                headword=headword,
                normalized_headword=normalized,
                phonetic=phonetic,
                definitions=definitions,
            ),
            line_number=line_number,
        )


_ERROR_MESSAGES = {
    "HEADWORD_REQUIRED": "A headword is required.",
    "HEADWORD_TOO_LONG": "The headword is longer than 200 characters.",
    "DEFINITION_EN_REQUIRED": "An English definition is required.",
    "DEFINITION_ZH_REQUIRED": "A Chinese definition is required.",
    "DEFINITION_PAIRING_INVALID": "English and Chinese definitions must be paired one-to-one.",
    "EXAMPLE_EN_REQUIRED": "An English example is required when a translation is supplied.",
    "EXAMPLE_PAIRING_INVALID": "English and translated examples must be paired one-to-one.",
    "PHONETIC_TOO_LONG": "The phonetic is longer than 200 characters.",
    "PART_OF_SPEECH_TOO_LONG": "The part of speech is longer than 64 characters.",
    "TXT_LINE_UNRELIABLE": "The TXT line could not be parsed into stable fields.",
}


class _ResultBuilder:
    def __init__(self) -> None:
        self.columns: list[str] = []
        self.entries: dict[str, ParsedEntry] = {}
        self.sample_rows: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.total_rows = 0

    def add_entry(self, entry: ParsedEntry, *, line_number: int) -> None:
        if not self.sample_rows or len(self.sample_rows) < 20:
            self.sample_rows.append(
                {
                    "line_number": line_number,
                    "headword": entry.headword,
                    "normalized_headword": entry.normalized_headword,
                    "phonetic": entry.phonetic,
                    "definitions": [
                        {
                            "part_of_speech": definition.part_of_speech,
                            "definition_en": definition.definition_en,
                            "definition_zh": definition.definition_zh,
                            "example_en": definition.examples[0].example_en
                            if definition.examples
                            else None,
                            "example_translation": definition.examples[0].example_zh
                            if definition.examples
                            else None,
                        }
                        for definition in entry.definitions
                    ],
                }
            )
        existing = self.entries.get(entry.normalized_headword)
        if existing is None:
            self.entries[entry.normalized_headword] = entry
            return
        self.warnings.append(
            {
                "line_number": line_number,
                "code": "DUPLICATE_MERGED",
                "message": "A duplicate headword was merged into the first occurrence.",
                "normalized_headword": entry.normalized_headword,
            }
        )
        existing.phonetic = existing.phonetic or entry.phonetic
        for definition in entry.definitions:
            if not _same_definition(existing.definitions, definition):
                existing.definitions.append(definition)
            else:
                _merge_examples(existing.definitions, definition)


def _same_definition(definitions: list[ParsedDefinition], candidate: ParsedDefinition) -> bool:
    return any(
        definition.part_of_speech == candidate.part_of_speech
        and definition.definition_en == candidate.definition_en
        and definition.definition_zh == candidate.definition_zh
        for definition in definitions
    )


def _merge_examples(definitions: list[ParsedDefinition], candidate: ParsedDefinition) -> None:
    for definition in definitions:
        if (
            definition.part_of_speech == candidate.part_of_speech
            and definition.definition_en == candidate.definition_en
            and definition.definition_zh == candidate.definition_zh
        ):
            known = {(item.example_en, item.example_zh) for item in definition.examples}
            for example in candidate.examples:
                if (example.example_en, example.example_zh) not in known:
                    definition.examples.append(example)
            return


def _parse_txt(text: str, builder: _ResultBuilder) -> tuple[list[str], dict[str, str | None]]:
    columns = list(CANONICAL_FIELDS)
    mapping = {field: field for field in CANONICAL_FIELDS}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        builder.total_rows += 1
        parts = [part.strip() for part in _split_txt_line(line)]
        if len(parts) < 2:
            builder.errors.append(
                {
                    "line_number": line_number,
                    "code": "TXT_LINE_UNRELIABLE",
                    "message": _ERROR_MESSAGES["TXT_LINE_UNRELIABLE"],
                }
            )
            continue
        values = parts[: len(CANONICAL_FIELDS)]
        values.extend([""] * (len(CANONICAL_FIELDS) - len(values)))
        if len(parts) > len(CANONICAL_FIELDS):
            values[-1] = " | ".join(parts[len(CANONICAL_FIELDS) - 1 :])
        row = dict(zip(columns, values, strict=True))
        _parse_structured_rows([row], columns=columns, mapping=mapping, result_builder=builder)
    return columns, mapping


def _split_txt_line(line: str) -> list[str]:
    for delimiter in ("\t", "|", ";", ","):
        if delimiter in line:
            return line.split(delimiter)
    return [line]


def parse_wordbook_bytes(
    raw: bytes,
    filename: str,
    *,
    mapping: dict[str, str | None] | None = None,
    ignored_columns: list[str] | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    max_entries: int = 20_000,
) -> ParseResult:
    if len(raw) > max_bytes:
        raise WordbookParseError(
            "IMPORT_FILE_TOO_LARGE",
            "The uploaded wordbook exceeds the permitted size.",
            details={"max_bytes": max_bytes},
        )
    if len(raw) == 0:
        raise WordbookParseError("IMPORT_FILE_EMPTY", "The uploaded file is empty.")

    suffix = Path(filename).suffix.casefold()
    if suffix not in {".csv", ".json", ".txt"}:
        raise WordbookParseError(
            "IMPORT_FILE_TYPE_UNSUPPORTED",
            "Only .csv, .json, and .txt wordbook files are supported.",
            details={"allowed_extensions": [".csv", ".json", ".txt"]},
        )
    text, encoding = _decode(raw)
    if any(token in raw[:512].lower() for token in (b"<html", b"<script", b"%pdf", b"pk\x03\x04")):
        raise WordbookParseError(
            "IMPORT_UNSAFE_CONTENT",
            "The file contains unsupported executable or document content.",
        )

    stripped = text.lstrip()
    json_like = suffix == ".json" or stripped.startswith(("[", "{"))
    detected_format: str
    delimiter: str | None = None
    builder = _ResultBuilder()
    columns: list[str]
    suggested: dict[str, str | None]

    if json_like:
        try:
            rows = _json_rows(text)
        except WordbookParseError:
            if suffix == ".json" or stripped.startswith(("[", "{")):
                raise
            rows = []
        if rows:
            detected_format = "json"
            columns = _dedupe_names(sorted({key for row in rows for key in row}))
            suggested = _suggest_mapping(columns)
        elif suffix == ".json":
            raise WordbookParseError("IMPORT_JSON_EMPTY", "The JSON file contains no word objects.")
        else:
            detected_format = "txt" if suffix == ".txt" else "csv"
            rows = []
    else:
        rows = []

    if detected_format == "json":
        resolved = _resolve_mapping(
            columns,
            suggested=suggested,
            mapping=mapping,
            ignored_columns=ignored_columns,
        )
        _parse_structured_rows(
            rows,
            columns=columns,
            mapping=resolved,
            result_builder=builder,
        )
    elif suffix == ".txt" and not json_like:
        columns = []
        detected_format = "txt"
        columns, suggested = _parse_txt_without_mapping(text, builder)
        resolved = _resolve_mapping(
            columns,
            suggested=suggested,
            mapping=mapping,
            ignored_columns=ignored_columns,
        )
    else:
        csv_rows = None
        try:
            csv_rows, delimiter = _csv_rows(text)
        except WordbookParseError:
            if suffix == ".csv":
                raise
        if csv_rows is not None:
            detected_format = "csv"
            columns = _dedupe_names(csv_rows[0])
            suggested = _suggest_mapping(columns)
            resolved = _resolve_mapping(
                columns,
                suggested=suggested,
                mapping=mapping,
                ignored_columns=ignored_columns,
            )
            structured = [dict(zip(columns, row, strict=False)) for row in csv_rows[1:] if row]
            _parse_structured_rows(
                structured,
                columns=columns,
                mapping=resolved,
                result_builder=builder,
            )
        else:
            detected_format = "txt"
            columns, suggested = _parse_txt_without_mapping(text, builder)
            resolved = _resolve_mapping(
                columns,
                suggested=suggested,
                mapping=mapping,
                ignored_columns=ignored_columns,
            )

    if len(builder.entries) > max_entries:
        raise WordbookParseError(
            "IMPORT_TOO_MANY_ENTRIES",
            "The wordbook contains too many logical entries.",
            details={"max_entries": max_entries, "logical_entries": len(builder.entries)},
        )
    entries = list(builder.entries.values())
    return ParseResult(
        detected_format=detected_format,
        encoding=encoding,
        delimiter=delimiter,
        columns=columns,
        suggested_mapping=suggested,
        mapping=resolved,
        ignored_columns=ignored_columns or [],
        entries=entries,
        sample_rows=builder.sample_rows,
        warnings=builder.warnings[:100],
        errors=builder.errors[:100],
        total_rows=builder.total_rows,
        valid_rows=len(entries),
        warning_count=len(builder.warnings),
        error_count=len(builder.errors),
    )


def _parse_txt_without_mapping(
    text: str, builder: _ResultBuilder
) -> tuple[list[str], dict[str, str | None]]:
    """Parse TXT lines while keeping the mapping independent of parsed rows."""
    columns = list(CANONICAL_FIELDS)
    mapping = {field: field for field in CANONICAL_FIELDS}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        builder.total_rows += 1
        parts = [part.strip() for part in _split_txt_line(line)]
        if len(parts) < 2:
            builder.errors.append(
                {
                    "line_number": line_number,
                    "code": "TXT_LINE_UNRELIABLE",
                    "message": _ERROR_MESSAGES["TXT_LINE_UNRELIABLE"],
                }
            )
            continue
        values = parts[: len(CANONICAL_FIELDS)]
        values.extend([""] * (len(CANONICAL_FIELDS) - len(values)))
        if len(parts) > len(CANONICAL_FIELDS):
            values[-1] = " | ".join(parts[len(CANONICAL_FIELDS) - 1 :])
        row = dict(zip(columns, values, strict=True))
        _parse_structured_rows([row], columns=columns, mapping=mapping, result_builder=builder)
    return columns, mapping


def parse_wordbook_json_document(result: ParseResult) -> dict[str, Any]:
    return {
        "format": "english-learn-wordbook-v1",
        "entries": result.canonical_entries(),
    }

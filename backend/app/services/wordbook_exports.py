from __future__ import annotations

import csv
import io
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ExportFormat = Literal["csv", "txt", "pdf"]

_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
DEFAULT_LATIN_FONT = _ASSET_DIR / "NotoSans-Regular.ttf"
DEFAULT_CJK_FONT = _ASSET_DIR / "NotoSansSC-Regular.ttf"
FONT_REGISTRATION_LOCK = threading.Lock()
_REGISTERED_FONTS: tuple[str, str] | None = None
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class WordbookExportError(RuntimeError):
    """A safe, user-observable export rendering failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ExportExample:
    example_en: str
    example_zh: str | None


@dataclass(frozen=True, slots=True)
class ExportDefinition:
    part_of_speech: str | None
    definition_en: str
    definition_zh: str
    examples: tuple[ExportExample, ...]


@dataclass(frozen=True, slots=True)
class ExportEntry:
    headword: str
    phonetic: str | None
    definitions: tuple[ExportDefinition, ...]


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    return _CONTROL_RE.sub("", value).strip()


def _export_rows(entries: tuple[ExportEntry, ...]) -> list[list[str]]:
    rows: list[list[str]] = []
    for entry in entries:
        definitions = entry.definitions or (None,)
        for definition in definitions:
            examples: tuple[ExportExample | None, ...] = (
                definition.examples if definition is not None and definition.examples else (None,)
            )
            for example in examples:
                rows.append(
                    [
                        _clean(entry.headword),
                        _clean(entry.phonetic),
                        _clean(definition.part_of_speech) if definition is not None else "",
                        _clean(definition.definition_en) if definition is not None else "",
                        _clean(definition.definition_zh) if definition is not None else "",
                        _clean(example.example_en) if example is not None else "",
                        _clean(example.example_zh) if example is not None else "",
                    ]
                )
    return rows


def _csv_safe(value: str) -> str:
    """Prevent spreadsheet applications from evaluating imported word data as formulas."""

    leading_trimmed = value.lstrip("\t\r ")
    if leading_trimmed.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _render_csv(entries: tuple[ExportEntry, ...]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(
        [
            "headword",
            "phonetic",
            "part_of_speech",
            "definition_en",
            "definition_zh",
            "example_en",
            "example_zh",
        ]
    )
    writer.writerows([[_csv_safe(cell) for cell in row] for row in _export_rows(entries)])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _render_txt(entries: tuple[ExportEntry, ...]) -> bytes:
    blocks: list[str] = []
    for index, entry in enumerate(entries, start=1):
        header = f"{index}. {_clean(entry.headword)}"
        if entry.phonetic:
            header += f"  /{_clean(entry.phonetic).strip('/')}/"
        lines = [header]
        for definition_index, definition in enumerate(entry.definitions, start=1):
            pos = f" [{_clean(definition.part_of_speech)}]" if definition.part_of_speech else ""
            lines.append(f"{definition_index}.{pos}")
            lines.append(f"EN: {_clean(definition.definition_en)}")
            lines.append(f"ZH: {_clean(definition.definition_zh)}")
            for example in definition.examples:
                lines.append(f"EX: {_clean(example.example_en)}")
                if example.example_zh:
                    lines.append(f"EX-ZH: {_clean(example.example_zh)}")
        blocks.append("\n".join(lines))
    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def _register_pdf_fonts(latin_font: Path, cjk_font: Path) -> tuple[str, str]:
    global _REGISTERED_FONTS
    if _REGISTERED_FONTS is not None:
        return _REGISTERED_FONTS
    if not latin_font.is_file() or not cjk_font.is_file():
        raise WordbookExportError(
            "WORDBOOK_PDF_FONT_UNAVAILABLE",
            "The configured PDF fonts are unavailable.",
        )
    with FONT_REGISTRATION_LOCK:
        if _REGISTERED_FONTS is None:
            pdfmetrics.registerFont(TTFont("WordbookLatin", str(latin_font)))
            pdfmetrics.registerFont(TTFont("WordbookCJK", str(cjk_font)))
            _REGISTERED_FONTS = ("WordbookLatin", "WordbookCJK")
    return _REGISTERED_FONTS


def _wrap_line(text: str, *, font_name: str, size: float, max_width: float) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and pdfmetrics.stringWidth(candidate, font_name, size) > max_width:
            lines.append(current.rstrip())
            current = character.lstrip()
        else:
            current = candidate
    if current or not lines:
        lines.append(current.rstrip())
    return lines


def _entry_draw_lines(entry: ExportEntry) -> list[tuple[str, Literal["latin", "cjk"], float]]:
    lines: list[tuple[str, Literal["latin", "cjk"], float]] = []
    header = _clean(entry.headword)
    if entry.phonetic:
        header += f"  /{_clean(entry.phonetic).strip('/')}/"
    lines.append((header, "latin", 8.5))
    for definition in entry.definitions:
        pos = f" [{_clean(definition.part_of_speech)}]" if definition.part_of_speech else ""
        if pos:
            lines.append((pos.strip(), "latin", 6.8))
        lines.append((f"EN: {_clean(definition.definition_en)}", "latin", 7.0))
        lines.append((f"ZH: {_clean(definition.definition_zh)}", "cjk", 7.0))
        for example in definition.examples:
            lines.append((f"EX: {_clean(example.example_en)}", "latin", 6.7))
            if example.example_zh:
                lines.append((f"EX-ZH: {_clean(example.example_zh)}", "cjk", 6.7))
    lines.append(("", "latin", 4.0))
    return lines


def _render_pdf(
    entries: tuple[ExportEntry, ...],
    *,
    page_rows: int,
    columns: int,
    latin_font: Path,
    cjk_font: Path,
) -> bytes:
    latin_name, cjk_name = _register_pdf_fonts(latin_font, cjk_font)
    page_width, page_height = A4
    margin_x = 24.0
    top_margin = 40.0
    bottom_margin = 24.0
    grid_width = page_width - (2 * margin_x)
    grid_height = page_height - top_margin - bottom_margin
    cell_width = grid_width / columns
    cell_height = grid_height / page_rows
    max_lines = max(1, int((cell_height - 5.0) / 8.0))
    text_width = max(10.0, cell_width - 8.0)

    chunks: list[list[tuple[str, Literal["latin", "cjk"], float]]] = []
    for entry in entries:
        source_lines = _entry_draw_lines(entry)
        wrapped: list[tuple[str, Literal["latin", "cjk"], float]] = []
        for text, font_kind, size in source_lines:
            font_name = latin_name if font_kind == "latin" else cjk_name
            for value in _wrap_line(text, font_name=font_name, size=size, max_width=text_width):
                wrapped.append((value, font_kind, size))
        first = True
        while wrapped:
            prefix: list[tuple[str, Literal["latin", "cjk"], float]] = []
            if not first and max_lines > 1:
                prefix = [("(continued)", "latin", 6.5)]
            content_capacity = max_lines - len(prefix)
            chunk = [*prefix, *wrapped[:content_capacity]]
            wrapped = wrapped[content_capacity:]
            chunks.append(chunk)
            first = False

    capacity = page_rows * columns
    pages = [chunks[index : index + capacity] for index in range(0, len(chunks), capacity)]
    if not pages:
        pages = [[]]

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    for page_number, page_chunks in enumerate(pages, start=1):
        pdf.setTitle("English wordbook export")
        pdf.setFont(latin_name, 10)
        pdf.drawString(margin_x, page_height - 24, f"Wordbook export - page {page_number}")
        for index, chunk in enumerate(page_chunks):
            column = index % columns
            row = index // columns
            x = margin_x + (column * cell_width)
            top_y = page_height - top_margin - (row * cell_height)
            pdf.setLineWidth(0.3)
            pdf.rect(x, top_y - cell_height, cell_width, cell_height, stroke=1, fill=0)
            y = top_y - 9.0
            for text, font_kind, size in chunk:
                font_name = latin_name if font_kind == "latin" else cjk_name
                pdf.setFont(font_name, size)
                pdf.drawString(x + 4.0, y, text)
                y -= 8.0
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def render_wordbook_export(
    entries: tuple[ExportEntry, ...],
    *,
    export_format: ExportFormat,
    page_rows: int,
    columns: int,
    latin_font: Path = DEFAULT_LATIN_FONT,
    cjk_font: Path = DEFAULT_CJK_FONT,
) -> bytes:
    if export_format == "csv":
        return _render_csv(entries)
    if export_format == "txt":
        return _render_txt(entries)
    if export_format == "pdf":
        if page_rows < 1 or columns < 1:
            raise WordbookExportError(
                "WORDBOOK_EXPORT_OPTIONS_INVALID",
                "PDF page rows and columns must be positive.",
            )
        return _render_pdf(
            entries,
            page_rows=page_rows,
            columns=columns,
            latin_font=latin_font,
            cjk_font=cjk_font,
        )
    raise WordbookExportError("WORDBOOK_EXPORT_FORMAT_INVALID", "Unsupported export format.")

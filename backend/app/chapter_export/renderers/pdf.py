"""Penulis berkas PDF ekspor bab."""

from __future__ import annotations

import asyncio
from pathlib import Path
import threading
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.chapter_export.markdown_blocks import (
    CodeBlock,
    DividerBlock,
    DocumentBlock,
    HeadingBlock,
    InlineSpan,
    ListBlock,
    ParagraphBlock,
    QuoteBlock,
    TableBlock,
    TableCell,
)
from app.chapter_export.renderers.base import iter_export_chapters, publish_rendering_stage


# Font bawaan reportlab memakai WinAnsiEncoding yang setara cp1252. Aksen Latin, tanda pisah, dan
# kutip cerdas tercakup, sementara aksara Han, Jepang, dan emoji tidak punya glyph sehingga akan
# tercetak sebagai kotak kosong tanpa memicu galat apa pun.
PDF_TEXT_ENCODING = "cp1252"
PDF_BODY_FONT = "Helvetica"
PDF_HEADING_FONT = "Helvetica-Bold"
PDF_ITALIC_FONT = "Helvetica-Oblique"
PDF_BOLD_ITALIC_FONT = "Helvetica-BoldOblique"

# Blok kode memuat diagram bergaris kotak yang tidak ada pada font bawaan, sekaligus menuntut lebar
# huruf seragam. Karena itu satu font monospace ber-Unicode dibundel bersama kode.
PDF_MONOSPACE_FONT = "OpenficMono"
MONOSPACE_FONT_PATH = Path(__file__).resolve().parent.parent / "fonts" / "DejaVuSansMono.ttf"

_FONT_LOCK = threading.Lock()
_FONT_REGISTERED = False

# Judul bab memakai tingkat kedua supaya judul volume tetap menjadi tingkat teratas, dan judul di
# dalam isi bab digeser agar bersarang di bawah judul babnya.
CONTENT_HEADING_OFFSET = 2
CONTENT_HEADING_MIN_SIZE = 11


class UnsupportedPdfCharacterError(RuntimeError):
    """Isi bab memuat aksara yang tidak dapat digambar font bawaan PDF."""


def ensure_monospace_font() -> str:
    """Mendaftarkan font monospace berkas sekali saja lalu mengembalikan namanya.

    Pendaftaran font reportlab bersifat global bagi proses, sehingga dijaga kunci agar dua tugas
    ekspor yang berjalan bersamaan tidak mendaftarkannya dua kali.
    """
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return PDF_MONOSPACE_FONT
    with _FONT_LOCK:
        if not _FONT_REGISTERED:
            pdfmetrics.registerFont(TTFont(PDF_MONOSPACE_FONT, str(MONOSPACE_FONT_PATH)))
            _FONT_REGISTERED = True
    return PDF_MONOSPACE_FONT


def find_unsupported_characters(text: str, limit: int = 6) -> list[str]:
    """Mengumpulkan aksara yang tidak terwakili font PDF bawaan, tanpa duplikat."""
    unsupported: list[str] = []
    seen: set[str] = set()
    for character in text:
        if character in seen:
            continue
        try:
            character.encode(PDF_TEXT_ENCODING)
        except UnicodeEncodeError:
            seen.add(character)
            unsupported.append(character)
            if len(unsupported) >= limit:
                break
    return unsupported


def _guard_pdf_text(text: str) -> str:
    """Menolak teks yang akan tercetak sebagai kotak kosong pada PDF.

    Kegagalan yang terang lebih berguna daripada berkas yang tampak berhasil namun tidak terbaca,
    karena itu tugas dihentikan dan pengguna diarahkan memakai format Word. Blok kode dikecualikan
    karena digambar memakai font monospace berkas yang cakupan aksaranya jauh lebih luas.
    """
    unsupported = find_unsupported_characters(text)
    if unsupported:
        sample = " ".join(unsupported)
        raise UnsupportedPdfCharacterError(
            "Ekspor PDF hanya mendukung aksara Latin, sedangkan naskah memuat aksara lain "
            f"({sample}). Gunakan format Word untuk naskah ini."
        )
    return text


def _span_font(style: str) -> str | None:
    if style == "bold":
        return PDF_HEADING_FONT
    if style == "italic":
        return PDF_ITALIC_FONT
    if style == "bold_italic":
        return PDF_BOLD_ITALIC_FONT
    if style == "code":
        return ensure_monospace_font()
    return None


def _spans_to_markup(spans: tuple[InlineSpan, ...]) -> str:
    """Mengubah potongan bergaya menjadi markah mini reportlab.

    Penegasan diterapkan lewat tag <font> alih-alih <b> dan <i>, karena penamaan font secara langsung
    tidak bergantung pada kemampuan reportlab menebak pasangan tebal atau miring sebuah font.
    """
    parts: list[str] = []
    for span in spans:
        text = xml_escape(_guard_pdf_text(span.text))
        font = _span_font(span.style)
        if font is None:
            parts.append(text)
        else:
            parts.append(f'<font face="{font}">{text}</font>')
    return "".join(parts)


def _cell_style(base: ParagraphStyle, cell: TableCell, bold: bool) -> ParagraphStyle:
    alignment = TA_JUSTIFY
    if cell.alignment == "right":
        alignment = TA_RIGHT
    elif cell.alignment == "center":
        alignment = TA_CENTER
    return ParagraphStyle(
        f"{base.name}-{cell.alignment}-{'h' if bold else 'b'}",
        parent=base,
        fontName=PDF_HEADING_FONT if bold else PDF_BODY_FONT,
        alignment=alignment,
    )


def _build_table(block: TableBlock, cell_style: ParagraphStyle) -> Flowable | None:
    columns = max(len(block.header), max((len(row) for row in block.rows), default=0))
    if columns == 0:
        return None

    data: list[list[Flowable]] = []
    if block.header:
        data.append(
            [
                Paragraph(_spans_to_markup(cell.spans), _cell_style(cell_style, cell, bold=True))
                for cell in _padded(block.header, columns)
            ]
        )
    for row in block.rows:
        data.append(
            [
                Paragraph(_spans_to_markup(cell.spans), _cell_style(cell_style, cell, bold=False))
                for cell in _padded(row, columns)
            ]
        )
    if not data:
        return None

    table = Table(data, hAlign="LEFT", repeatRows=1 if block.header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#8a8a8a")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if block.header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ededed")))
    table.setStyle(TableStyle(commands))
    return table


def _padded(cells: tuple[TableCell, ...], columns: int) -> list[TableCell]:
    """Menyamakan jumlah sel setiap baris, karena Table reportlab menuntut baris berukuran sama."""
    padded = list(cells[:columns])
    while len(padded) < columns:
        padded.append(TableCell(spans=()))
    return padded


def _block_flowables(
    block: DocumentBlock,
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    if isinstance(block, HeadingBlock):
        return [Paragraph(_spans_to_markup(block.spans), _content_heading_style(block.level, styles))]
    if isinstance(block, ParagraphBlock):
        return [Paragraph(_spans_to_markup(block.spans), styles["body"])]
    if isinstance(block, QuoteBlock):
        return [Paragraph(_spans_to_markup(block.spans), styles["quote"])]
    if isinstance(block, ListBlock):
        flowables: list[Flowable] = []
        for index, item in enumerate(block.items):
            marker = f"{block.start + index}." if block.ordered else "\u2022"
            markup = f'<font face="{PDF_BODY_FONT}">{marker}</font>&nbsp;{_spans_to_markup(item.spans)}'
            flowables.append(Paragraph(markup, styles["list"]))
        return flowables
    if isinstance(block, TableBlock):
        table = _build_table(block, styles["cell"])
        return [table, Spacer(1, 6)] if table is not None else []
    if isinstance(block, CodeBlock):
        # Diagram teks tidak boleh dirapatkan spasinya maupun dilipat, jadi dipakai Preformatted
        # dengan font monospace berkas yang cakupan aksaranya menampung garis kotak.
        return [Preformatted(block.text, styles["code"]), Spacer(1, 6)]
    if isinstance(block, DividerBlock):
        return [
            Spacer(1, 4),
            HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#b0b0b0")),
            Spacer(1, 6),
        ]
    return []


def _content_heading_style(level: int, styles: dict[str, ParagraphStyle]) -> ParagraphStyle:
    """Menurunkan gaya judul isi bab agar tingkatannya terlihat tanpa menyaingi judul bab."""
    size = max(CONTENT_HEADING_MIN_SIZE, 15 - level)
    return ParagraphStyle(
        f"OpenficContentHeading{level}",
        parent=styles["chapter"],
        fontSize=size,
        leading=size + 5,
        spaceBefore=8,
        spaceAfter=4,
    )


def _build_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    volume_style = ParagraphStyle(
        "OpenficVolume",
        parent=sample["Heading1"],
        fontName=PDF_HEADING_FONT,
        fontSize=18,
        leading=24,
        spaceBefore=0,
        spaceAfter=12,
    )
    chapter_style = ParagraphStyle(
        "OpenficChapter",
        parent=sample["Heading2"],
        fontName=PDF_HEADING_FONT,
        fontSize=14,
        leading=20,
        spaceBefore=0,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "OpenficBody",
        parent=sample["BodyText"],
        fontName=PDF_BODY_FONT,
        fontSize=11,
        leading=17,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
    )
    return {
        "volume": volume_style,
        "chapter": chapter_style,
        "body": body_style,
        "quote": ParagraphStyle(
            "OpenficQuote",
            parent=body_style,
            leftIndent=14,
            rightIndent=10,
            fontName=PDF_ITALIC_FONT,
            textColor=colors.HexColor("#3d3d3d"),
        ),
        "list": ParagraphStyle(
            "OpenficList",
            parent=body_style,
            leftIndent=16,
            alignment=TA_JUSTIFY,
            spaceAfter=3,
        ),
        "cell": ParagraphStyle(
            "OpenficCell",
            parent=body_style,
            fontSize=9,
            leading=13,
            spaceAfter=0,
        ),
        "code": ParagraphStyle(
            "OpenficCode",
            parent=body_style,
            fontName=ensure_monospace_font(),
            fontSize=8.5,
            leading=11,
            spaceAfter=0,
            alignment=0,
        ),
    }


async def render_pdf(context, payload: dict[str, Any], part_path: Path) -> None:
    """Merakit alur PDF lalu membangunnya di utas terpisah.

    Sama seperti DOCX, reportlab membutuhkan seluruh alur cerita sebelum dapat menghitung halaman,
    sehingga pembangunan dijalankan lewat utas agar perulangan peristiwa tidak terhalang.
    """
    styles = _build_styles()
    story: list[Flowable] = []
    total = 0

    async for chapter in iter_export_chapters(context, payload):
        if not chapter.is_first:
            story.append(PageBreak())
        if chapter.volume_heading is not None:
            story.append(
                Paragraph(xml_escape(_guard_pdf_text(chapter.volume_heading)), styles["volume"])
            )
        heading = Paragraph(xml_escape(_guard_pdf_text(chapter.title)), styles["chapter"])

        if chapter.blocks:
            rendered: list[Flowable] = []
            for block in chapter.blocks:
                rendered.extend(_block_flowables(block, styles))
            # Judul bab tidak boleh tertinggal sendiri di dasar halaman, jadi diikat dengan flowable
            # pertama isinya.
            if rendered:
                story.append(KeepTogether([heading, rendered[0]]))
                story.extend(rendered[1:])
            else:
                story.append(heading)
        else:
            lines = [line for line in chapter.content.split("\n") if line.strip()]
            first_paragraph = (
                Paragraph(xml_escape(_guard_pdf_text(lines[0])), styles["body"])
                if lines
                else Spacer(1, 0)
            )
            story.append(KeepTogether([heading, first_paragraph]))
            for line in lines[1:]:
                story.append(Paragraph(xml_escape(_guard_pdf_text(line)), styles["body"]))
        total += 1

    await context.check_cancelled()
    await publish_rendering_stage(context, total)
    document = SimpleDocTemplate(
        str(part_path),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )
    await asyncio.to_thread(document.build, story)

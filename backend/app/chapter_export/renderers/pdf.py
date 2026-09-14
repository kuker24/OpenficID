"""Penulis berkas PDF ekspor bab."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from app.chapter_export.renderers.base import iter_export_chapters, publish_rendering_stage


# Font bawaan reportlab memakai WinAnsiEncoding yang setara cp1252. Aksen Latin, tanda pisah, dan
# kutip cerdas tercakup, sementara aksara Han, Jepang, dan emoji tidak punya glyph sehingga akan
# tercetak sebagai kotak kosong tanpa memicu galat apa pun.
PDF_TEXT_ENCODING = "cp1252"
PDF_BODY_FONT = "Helvetica"
PDF_HEADING_FONT = "Helvetica-Bold"


class UnsupportedPdfCharacterError(RuntimeError):
    """Isi bab memuat aksara yang tidak dapat digambar font bawaan PDF."""


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
    karena itu tugas dihentikan dan pengguna diarahkan memakai format Word.
    """
    unsupported = find_unsupported_characters(text)
    if unsupported:
        sample = " ".join(unsupported)
        raise UnsupportedPdfCharacterError(
            "Ekspor PDF hanya mendukung aksara Latin, sedangkan naskah memuat aksara lain "
            f"({sample}). Gunakan format Word untuk naskah ini."
        )
    return text


def _build_styles() -> tuple[ParagraphStyle, ParagraphStyle, ParagraphStyle]:
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
    return volume_style, chapter_style, body_style


async def render_pdf(context, payload: dict[str, Any], part_path: Path) -> None:
    """Merakit alur PDF lalu membangunnya di utas terpisah.

    Sama seperti DOCX, reportlab membutuhkan seluruh alur cerita sebelum dapat menghitung halaman,
    sehingga pembangunan dijalankan lewat utas agar perulangan peristiwa tidak terhalang.
    """
    volume_style, chapter_style, body_style = _build_styles()
    story: list[Flowable] = []
    total = 0

    async for chapter in iter_export_chapters(context, payload):
        if not chapter.is_first:
            story.append(PageBreak())
        if chapter.volume_heading is not None:
            story.append(Paragraph(xml_escape(_guard_pdf_text(chapter.volume_heading)), volume_style))
        heading = Paragraph(xml_escape(_guard_pdf_text(chapter.title)), chapter_style)
        # Judul bab tidak boleh tertinggal sendiri di dasar halaman, jadi diikat dengan paragraf
        # pertama isinya.
        lines = [line for line in chapter.content.split("\n") if line.strip()]
        first_paragraph = (
            Paragraph(xml_escape(_guard_pdf_text(lines[0])), body_style) if lines else Spacer(1, 0)
        )
        story.append(KeepTogether([heading, first_paragraph]))
        for line in lines[1:]:
            story.append(Paragraph(xml_escape(_guard_pdf_text(line)), body_style))
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

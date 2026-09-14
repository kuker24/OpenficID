"""Penulis berkas DOCX ekspor bab."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

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
)
from app.chapter_export.renderers.base import iter_export_chapters, publish_rendering_stage


BODY_FONT = "Calibri"
# Diagram teks memerlukan lebar huruf yang seragam. Word memakai font sistem, sehingga cukup
# menamainya tanpa perlu membundel berkas font seperti pada PDF.
MONOSPACE_FONT = "DejaVu Sans Mono"
BODY_SIZE = Pt(11)
CODE_SIZE = Pt(9)

# Judul bab memakai Heading 2 supaya judul volume di Heading 1 tetap menjadi tingkat teratas.
# Judul di dalam isi bab digeser dua tingkat agar bersarang di bawah judul babnya sendiri.
CHAPTER_HEADING_LEVEL = 2
CONTENT_HEADING_OFFSET = 2
MAX_HEADING_LEVEL = 9


def _apply_span(run, span: InlineSpan) -> None:
    if span.style in ("bold", "bold_italic"):
        run.bold = True
    if span.style in ("italic", "bold_italic"):
        run.italic = True
    if span.style == "code":
        run.font.name = MONOSPACE_FONT


def _write_spans(paragraph, spans: tuple[InlineSpan, ...]) -> None:
    for span in spans:
        _apply_span(paragraph.add_run(span.text), span)


def _write_code_block(document, block: CodeBlock) -> None:
    """Menulis blok kode sebagai satu paragraf berhuruf seragam.

    Seluruh baris ditempatkan pada satu paragraf dengan pemenggalan baris di dalamnya, sehingga Word
    tidak menyisipkan jarak antarparagraf yang akan merenggangkan diagram.
    """
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(6)
    lines = block.text.split("\n")
    for index, line in enumerate(lines):
        run = paragraph.add_run(line)
        run.font.name = MONOSPACE_FONT
        run.font.size = CODE_SIZE
        if index < len(lines) - 1:
            run.add_break()


def _write_table(document, block: TableBlock) -> None:
    columns = max(
        len(block.header),
        max((len(row) for row in block.rows), default=0),
    )
    if columns == 0:
        return

    table = document.add_table(rows=0, cols=columns)
    table.style = "Table Grid"
    alignments = [cell.alignment for cell in block.header] if block.header else []

    if block.header:
        cells = table.add_row().cells
        for index, cell in enumerate(block.header):
            paragraph = cells[index].paragraphs[0]
            _write_spans(paragraph, cell.spans)
            # Baris kepala ditebalkan lewat gaya run karena gaya "Table Grid" tidak menandainya.
            for run in paragraph.runs:
                run.bold = True
            _align_paragraph(paragraph, cell.alignment)

    for row in block.rows:
        cells = table.add_row().cells
        for index, cell in enumerate(row):
            if index >= columns:
                break
            paragraph = cells[index].paragraphs[0]
            _write_spans(paragraph, cell.spans)
            alignment = cell.alignment
            if alignment == "left" and index < len(alignments):
                alignment = alignments[index]
            _align_paragraph(paragraph, alignment)


def _align_paragraph(paragraph, alignment: str) -> None:
    if alignment == "right":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif alignment == "center":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _write_block(document, block: DocumentBlock) -> None:
    if isinstance(block, HeadingBlock):
        level = min(block.level + CONTENT_HEADING_OFFSET, MAX_HEADING_LEVEL)
        _write_spans(document.add_heading("", level=level), block.spans)
    elif isinstance(block, ParagraphBlock):
        _write_spans(document.add_paragraph(), block.spans)
    elif isinstance(block, QuoteBlock):
        paragraph = document.add_paragraph(style="Quote")
        _write_spans(paragraph, block.spans)
    elif isinstance(block, ListBlock):
        style = "List Number" if block.ordered else "List Bullet"
        for item in block.items:
            _write_spans(document.add_paragraph(style=style), item.spans)
    elif isinstance(block, TableBlock):
        _write_table(document, block)
    elif isinstance(block, CodeBlock):
        _write_code_block(document, block)
    elif isinstance(block, DividerBlock):
        # Word tidak punya flowable garis pemisah, jadi dipakai paragraf kosong sebagai jeda visual.
        document.add_paragraph()


async def render_docx(context, payload: dict[str, Any], part_path: Path) -> None:
    """Merakit dokumen Word lalu menyimpannya di utas terpisah.

    Berbeda dari TXT, python-docx menyusun seluruh dokumen di memori sebelum dapat disimpan,
    sehingga penyimpanan dijalankan lewat utas agar perulangan peristiwa tidak terhalang.
    Judul memakai gaya Heading bawaan Word supaya panel navigasi dokumen langsung berfungsi.
    """
    document = Document()
    body_style = document.styles["Normal"]
    font = getattr(body_style, "font", None)
    if font is not None:
        font.name = BODY_FONT
        font.size = BODY_SIZE

    total = 0
    async for chapter in iter_export_chapters(context, payload):
        if chapter.volume_heading is not None:
            heading = document.add_heading(chapter.volume_heading, level=1)
            if not chapter.is_first:
                heading.paragraph_format.page_break_before = True
        chapter_heading = document.add_heading(chapter.title, level=CHAPTER_HEADING_LEVEL)
        if chapter.volume_heading is None and not chapter.is_first:
            chapter_heading.paragraph_format.page_break_before = True

        if chapter.blocks:
            for block in chapter.blocks:
                _write_block(document, block)
        else:
            # Isi bab fiksi tersimpan sebagai teks polos berbasis baris, jadi setiap baris menjadi
            # satu paragraf agar jeda yang ditulis pengarang tetap terlihat di Word.
            for line in chapter.content.split("\n"):
                document.add_paragraph(line)
        total += 1

    await context.check_cancelled()
    await publish_rendering_stage(context, total)
    await asyncio.to_thread(document.save, str(part_path))

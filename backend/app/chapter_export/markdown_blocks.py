"""Penguraian Markdown isi bab menjadi blok yang netral terhadap format keluaran.

Penulis DOCX dan PDF membutuhkan struktur yang sama: judul bertingkat, paragraf, daftar, tabel, dan
blok kode. Penguraian diletakkan di satu tempat agar kedua penulis tidak menafsirkan Markdown dengan
caranya sendiri lalu menghasilkan dokumen yang berbeda dari sumber yang sama.

Blok yang dihasilkan sengaja dangkal: daftar tidak bersarang dan sel tabel hanya memuat rentetan
teks. Naskah non-fiksi memakai Markdown untuk struktur bacaan, bukan untuk tata letak rumit, dan
struktur dangkal jauh lebih mudah dipetakan ke dua format keluaran sekaligus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from markdown_it import MarkdownIt
from markdown_it.token import Token


# Preset gfm-like menyalakan tabel dan penautan otomatis sekaligus. Penautan otomatis memerlukan
# linkify-it-py yang tidak dipasang, dan ketiadaannya memunculkan ModuleNotFoundError saat penguraian
# alih-alih saat impor, karena itu penautan dimatikan secara eksplisit.
def _build_parser() -> MarkdownIt:
    return MarkdownIt("gfm-like").disable("linkify")


_PARSER = _build_parser()

InlineStyle = Literal["plain", "bold", "italic", "bold_italic", "code"]

BlockAlignment = Literal["left", "center", "right"]


@dataclass(frozen=True)
class InlineSpan:
    """Sepotong teks beserta penegasan yang berlaku padanya."""

    text: str
    style: InlineStyle = "plain"


@dataclass(frozen=True)
class HeadingBlock:
    """Judul bagian beserta tingkatannya, 1 sampai 6."""

    level: int
    spans: tuple[InlineSpan, ...]


@dataclass(frozen=True)
class ParagraphBlock:
    """Satu paragraf prosa."""

    spans: tuple[InlineSpan, ...]


@dataclass(frozen=True)
class QuoteBlock:
    """Kutipan blok, dirapatkan menjadi paragraf berindentasi."""

    spans: tuple[InlineSpan, ...]


@dataclass(frozen=True)
class ListItem:
    """Satu butir daftar."""

    spans: tuple[InlineSpan, ...]


@dataclass(frozen=True)
class ListBlock:
    """Daftar berbutir atau berangka."""

    ordered: bool
    items: tuple[ListItem, ...]
    start: int = 1


@dataclass(frozen=True)
class TableCell:
    """Satu sel tabel."""

    spans: tuple[InlineSpan, ...]
    alignment: BlockAlignment = "left"


@dataclass(frozen=True)
class TableBlock:
    """Tabel beserta baris kepalanya bila ada."""

    header: tuple[TableCell, ...]
    rows: tuple[tuple[TableCell, ...], ...]


@dataclass(frozen=True)
class CodeBlock:
    """Blok kode atau diagram, ditulis apa adanya dengan huruf berlebar seragam."""

    text: str
    language: str | None = None


@dataclass(frozen=True)
class DividerBlock:
    """Garis pemisah antarbagian."""


DocumentBlock = (
    HeadingBlock
    | ParagraphBlock
    | QuoteBlock
    | ListBlock
    | TableBlock
    | CodeBlock
    | DividerBlock
)


@dataclass
class _ListState:
    ordered: bool
    start: int
    items: list[ListItem] = field(default_factory=list)


def _style(bold: int, italic: int) -> InlineStyle:
    if bold and italic:
        return "bold_italic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "plain"


def _merge_spans(spans: list[InlineSpan]) -> tuple[InlineSpan, ...]:
    """Menggabungkan potongan bersebelahan yang bergaya sama lalu membuang sisa kosong."""
    merged: list[InlineSpan] = []
    for span in spans:
        if not span.text:
            continue
        if merged and merged[-1].style == span.style:
            merged[-1] = InlineSpan(merged[-1].text + span.text, span.style)
        else:
            merged.append(span)
    while merged and not merged[-1].text.strip():
        merged.pop()
    while merged and not merged[0].text.strip():
        merged.pop(0)
    return tuple(merged)


def _inline_spans(token: Token | None) -> tuple[InlineSpan, ...]:
    """Mengubah satu token inline menjadi rentetan potongan bergaya.

    Pemenggalan baris di dalam paragraf, baik lunak maupun keras, diseragamkan menjadi spasi. Kedua
    format keluaran merapatkan spasi putih di dalam paragraf, sehingga menyimpan pemenggalan itu
    hanya akan menambah rumit tanpa mengubah hasil cetak.
    """
    if token is None:
        return ()
    spans: list[InlineSpan] = []
    bold = 0
    italic = 0
    for child in token.children or []:
        kind = child.type
        if kind == "text":
            spans.append(InlineSpan(child.content, _style(bold, italic)))
        elif kind == "code_inline":
            spans.append(InlineSpan(child.content, "code"))
        elif kind == "strong_open":
            bold += 1
        elif kind == "strong_close":
            bold = max(0, bold - 1)
        elif kind == "em_open":
            italic += 1
        elif kind == "em_close":
            italic = max(0, italic - 1)
        elif kind in ("softbreak", "hardbreak"):
            spans.append(InlineSpan(" ", "plain"))
        elif kind == "image":
            # Gambar tidak pernah muncul pada isi bab, namun teks alternatifnya tetap dipertahankan
            # supaya tidak ada kalimat yang hilang begitu saja.
            alt = child.attrGet("alt") or child.content
            if isinstance(alt, str):
                spans.append(InlineSpan(alt, _style(bold, italic)))
    return _merge_spans(spans)


def spans_to_text(spans: tuple[InlineSpan, ...]) -> str:
    """Merangkai potongan bergaya menjadi teks biasa."""
    return "".join(span.text for span in spans)


def _matching_close(tokens: list[Token], open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(tokens)):
        depth += tokens[index].nesting
        if depth == 0 and index > open_index:
            return index
    return len(tokens) - 1


def _first_inline(tokens: list[Token], start: int, end: int) -> Token | None:
    for index in range(start, end):
        if tokens[index].type == "inline":
            return tokens[index]
    return None


def _collect_inline_spans(tokens: list[Token], start: int, end: int) -> tuple[InlineSpan, ...]:
    """Merapatkan seluruh paragraf pada satu rentang menjadi satu rentetan potongan."""
    spans: list[InlineSpan] = []
    for index in range(start, end):
        if tokens[index].type != "inline":
            continue
        if spans:
            spans.append(InlineSpan(" ", "plain"))
        spans.extend(_inline_spans(tokens[index]))
    return _merge_spans(spans)


def _cell_alignment(token: Token) -> BlockAlignment:
    style = token.attrGet("style")
    if not isinstance(style, str):
        return "left"
    if "right" in style:
        return "right"
    if "center" in style:
        return "center"
    return "left"


def _parse_table(tokens: list[Token], start: int, end: int) -> TableBlock | None:
    header: list[TableCell] = []
    rows: list[tuple[TableCell, ...]] = []
    current: list[TableCell] = []
    in_header = False
    index = start + 1
    while index < end:
        token = tokens[index]
        kind = token.type
        if kind == "thead_open":
            in_header = True
        elif kind == "thead_close":
            in_header = False
        elif kind == "tr_open":
            current = []
        elif kind == "tr_close":
            if in_header and not header:
                header = current
            elif current:
                rows.append(tuple(current))
        elif kind in ("th_open", "td_open"):
            close = _matching_close(tokens, index)
            current.append(
                TableCell(
                    spans=_inline_spans(_first_inline(tokens, index, close)),
                    alignment=_cell_alignment(token),
                )
            )
            index = close
        index += 1
    if not header and not rows:
        return None
    return TableBlock(header=tuple(header), rows=tuple(rows))


def _parse_list(tokens: list[Token], start: int, end: int, ordered: bool) -> ListBlock | None:
    """Menguraikan daftar dengan mendataran butir bersarang ke tingkat yang sama.

    Naskah non-fiksi memakai daftar untuk merinci, bukan untuk menyusun pohon, dan struktur mendatar
    jauh lebih mudah dipetakan ke DOCX maupun PDF secara seragam.
    """
    raw_start = tokens[start].attrGet("start")
    first_number = int(raw_start) if isinstance(raw_start, (int, str)) and str(raw_start).isdigit() else 1
    items: list[ListItem] = []
    index = start + 1
    while index < end:
        if tokens[index].type != "list_item_open":
            index += 1
            continue
        close = _matching_close(tokens, index)
        spans = _collect_inline_spans(tokens, index, close)
        if spans:
            items.append(ListItem(spans=spans))
        index = close + 1
    if not items:
        return None
    return ListBlock(ordered=ordered, items=tuple(items), start=first_number)


def _consume_blocks(tokens: list[Token], start: int, end: int) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    index = start
    while index < end:
        token = tokens[index]
        kind = token.type
        if kind == "heading_open":
            close = _matching_close(tokens, index)
            level = int(token.tag[1:]) if token.tag[1:].isdigit() else 1
            spans = _inline_spans(_first_inline(tokens, index, close))
            if spans:
                blocks.append(HeadingBlock(level=level, spans=spans))
            index = close + 1
        elif kind == "paragraph_open":
            close = _matching_close(tokens, index)
            spans = _inline_spans(_first_inline(tokens, index, close))
            if spans:
                blocks.append(ParagraphBlock(spans=spans))
            index = close + 1
        elif kind == "blockquote_open":
            close = _matching_close(tokens, index)
            spans = _collect_inline_spans(tokens, index, close)
            if spans:
                blocks.append(QuoteBlock(spans=spans))
            index = close + 1
        elif kind in ("bullet_list_open", "ordered_list_open"):
            close = _matching_close(tokens, index)
            parsed = _parse_list(tokens, index, close, ordered=kind == "ordered_list_open")
            if parsed is not None:
                blocks.append(parsed)
            index = close + 1
        elif kind == "table_open":
            close = _matching_close(tokens, index)
            table = _parse_table(tokens, index, close)
            if table is not None:
                blocks.append(table)
            index = close + 1
        elif kind in ("fence", "code_block"):
            text = token.content.rstrip("\n")
            if text:
                language = token.info.strip() or None
                blocks.append(CodeBlock(text=text, language=language))
            index += 1
        elif kind == "hr":
            blocks.append(DividerBlock())
            index += 1
        else:
            index += 1
    return blocks


def parse_markdown_blocks(content: str) -> tuple[DocumentBlock, ...]:
    """Menguraikan isi bab bermarkdown menjadi blok yang netral terhadap format keluaran."""
    if not content.strip():
        return ()
    tokens = _PARSER.parse(content)
    return tuple(_consume_blocks(tokens, 0, len(tokens)))

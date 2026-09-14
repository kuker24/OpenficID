from app.chapter_export.markdown_blocks import (
    CodeBlock,
    DividerBlock,
    HeadingBlock,
    ListBlock,
    ParagraphBlock,
    QuoteBlock,
    TableBlock,
    parse_markdown_blocks,
    spans_to_text,
)


def test_parse_returns_nothing_for_blank_content() -> None:
    assert parse_markdown_blocks("") == ()
    assert parse_markdown_blocks("   \n\n  ") == ()


def test_parse_reads_heading_levels() -> None:
    blocks = parse_markdown_blocks("# Satu\n\n### Tiga")
    assert [type(block) for block in blocks] == [HeadingBlock, HeadingBlock]
    assert [block.level for block in blocks if isinstance(block, HeadingBlock)] == [1, 3]
    assert spans_to_text(blocks[0].spans) == "Satu"


def test_parse_keeps_inline_emphasis_styles() -> None:
    blocks = parse_markdown_blocks("Ada *miring*, **tebal**, dan `kode` di sini.")
    assert isinstance(blocks[0], ParagraphBlock)
    styles = {span.style: span.text for span in blocks[0].spans}
    assert styles["italic"] == "miring"
    assert styles["bold"] == "tebal"
    assert styles["code"] == "kode"


def test_parse_marks_nested_emphasis_as_bold_italic() -> None:
    blocks = parse_markdown_blocks("Ini ***keduanya*** sekaligus.")
    assert any(span.style == "bold_italic" for span in blocks[0].spans)


def test_parse_flattens_line_breaks_inside_paragraph() -> None:
    """Kedua format keluaran merapatkan spasi di dalam paragraf, jadi pemenggalan diseragamkan."""
    blocks = parse_markdown_blocks("Baris satu\nbaris dua.")
    assert len(blocks) == 1
    assert spans_to_text(blocks[0].spans) == "Baris satu baris dua."


def test_parse_reads_table_with_alignment_and_emphasis() -> None:
    content = "| Dimensi | Nilai |\n| :--- | ---: |\n| **Otoritas** | 42 |"
    blocks = parse_markdown_blocks(content)
    assert len(blocks) == 1
    table = blocks[0]
    assert isinstance(table, TableBlock)
    assert [spans_to_text(cell.spans) for cell in table.header] == ["Dimensi", "Nilai"]
    assert [cell.alignment for cell in table.header] == ["left", "right"]
    assert [spans_to_text(cell.spans) for cell in table.rows[0]] == ["Otoritas", "42"]
    assert table.rows[0][0].spans[0].style == "bold"


def test_parse_reads_ordered_and_bullet_lists() -> None:
    blocks = parse_markdown_blocks("1. Satu\n2. Dua\n\n- Butir\n- Lain")
    lists = [block for block in blocks if isinstance(block, ListBlock)]
    assert [block.ordered for block in lists] == [True, False]
    assert [spans_to_text(item.spans) for item in lists[0].items] == ["Satu", "Dua"]
    assert [spans_to_text(item.spans) for item in lists[1].items] == ["Butir", "Lain"]


def test_parse_keeps_ordered_list_start_number() -> None:
    blocks = parse_markdown_blocks("3. Tiga\n4. Empat")
    assert isinstance(blocks[0], ListBlock)
    assert blocks[0].start == 3


def test_parse_keeps_code_block_lines_verbatim() -> None:
    """Diagram teks kehilangan maknanya bila spasinya dirapatkan atau barisnya digabung."""
    content = "```\n[ META-LEADER ]\n\u250c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u2510\n```"
    blocks = parse_markdown_blocks(content)
    assert len(blocks) == 1
    assert isinstance(blocks[0], CodeBlock)
    assert blocks[0].text.splitlines() == ["[ META-LEADER ]", "\u250c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u2510"]


def test_parse_reads_code_block_language() -> None:
    blocks = parse_markdown_blocks("```python\nprint(1)\n```")
    assert isinstance(blocks[0], CodeBlock)
    assert blocks[0].language == "python"


def test_parse_reads_blockquote_and_divider() -> None:
    blocks = parse_markdown_blocks("> Kutipan penting.\n\n---")
    assert [type(block) for block in blocks] == [QuoteBlock, DividerBlock]
    assert spans_to_text(blocks[0].spans) == "Kutipan penting."


def test_parse_joins_multi_paragraph_blockquote() -> None:
    blocks = parse_markdown_blocks("> Baris satu.\n>\n> Baris dua.")
    quotes = [block for block in blocks if isinstance(block, QuoteBlock)]
    assert len(quotes) == 1
    assert spans_to_text(quotes[0].spans) == "Baris satu. Baris dua."


def test_parse_treats_plain_prose_as_paragraphs() -> None:
    """Naskah tanpa penanda tetap terurai menjadi paragraf, bukan menjadi kosong."""
    blocks = parse_markdown_blocks("Malam turun perlahan.\n\nAngin membawa bau tanah basah.")
    assert [type(block) for block in blocks] == [ParagraphBlock, ParagraphBlock]


def test_parse_does_not_autolink_bare_urls() -> None:
    """Preset gfm-like menyalakan penautan otomatis yang paketnya tidak dipasang, jadi dimatikan."""
    blocks = parse_markdown_blocks("Kunjungi contoh.com untuk rinciannya.")
    assert spans_to_text(blocks[0].spans) == "Kunjungi contoh.com untuk rinciannya."

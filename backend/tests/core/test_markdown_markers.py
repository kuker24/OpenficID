import pytest

from app.core.markdown_markers import contains_markdown, find_markdown_markers


@pytest.mark.parametrize(
    ("label", "content"),
    [
        ("judul di baris pertama", "# BAB 1: PARADOKS META-KEPEMIMPINAN\n\nIsi bab."),
        ("judul di tengah naskah", "Paragraf.\n\n### Pengantar: Runtuhnya Hukum\n\nLanjut."),
        ("judul berindentasi", "Paragraf.\n\n   ## Subbagian\n\nLanjut."),
        ("penegasan tebal", "Fenomena ini adalah **Paradoks Meta-Kepemimpinan** yang nyata."),
        ("baris tabel", "| Dimensi | Memimpin |\n| :--- | :--- |\n| Otoritas | Mandat |"),
        ("kutipan blok", "> Kekuasaan sejati bukanlah seni menaklukkan."),
        ("garis pemisah", "Paragraf.\n\n---\n\nParagraf lain."),
        ("blok kode", "Diagram:\n\n```\n[ META-LEADER ]\n```"),
        ("blok kode gelombang", "Diagram:\n\n~~~\nskema\n~~~"),
    ],
)
def test_find_markdown_markers_detects_structural_syntax(label: str, content: str) -> None:
    assert find_markdown_markers(content), label
    assert contains_markdown(content), label


@pytest.mark.parametrize(
    ("label", "content"),
    [
        ("tanda pisah dialog", "\u2014 Kau yakin? tanyanya.\n\u2014 Tentu saja."),
        ("tanda pisah em", "Ia berhenti\u2014lalu menoleh perlahan."),
        ("penomoran pengarang", "1. Pertama ia melangkah.\n2. Kemudian ia berhenti."),
        ("butir sederhana", "- Ambil pedang\n- Pergi ke utara"),
        ("bintang tunggal", "Ia bergumam, *entahlah*, lalu pergi."),
        ("satu pipa di tengah", "Nilainya 3 | 4 dalam catatan itu."),
        ("tagar tanpa spasi", "Ia menulis #1 di papan tulis."),
        ("hash rapat", "##bukan judul"),
        ("kutip cerdas", "\u201cKau datang juga,\u201d katanya."),
        ("elipsis", "Entah... mungkin besok."),
        ("prosa biasa", "Malam turun perlahan. Angin membawa bau tanah basah."),
        ("naskah kosong", ""),
    ],
)
def test_find_markdown_markers_leaves_plain_prose_alone(label: str, content: str) -> None:
    """Salah tuduh menolak naskah yang sah, jadi penanda yang meragukan sengaja tidak diperiksa.

    Daftar berbutir dan berangka termasuk yang dilewatkan, karena "- " di awal baris dapat menjadi
    tanda pisah dialog dan "1. " dapat menjadi penomoran yang memang ditulis pengarang.
    """
    assert find_markdown_markers(content) == [], label
    assert not contains_markdown(content), label


def test_find_markdown_markers_names_the_marker_found() -> None:
    """Pesan galat perlu menunjuk penanda yang sebenarnya ditemukan agar dapat ditindaklanjuti."""
    assert find_markdown_markers("# Judul") == ["judul (#)"]
    assert find_markdown_markers("Ini **tebal**.") == ["penegasan tebal (**)"]


def test_find_markdown_markers_reports_multiple_markers_without_duplicates() -> None:
    content = "# Judul\n\nIsi **tebal**.\n\n---\n\n> kutipan"
    markers = find_markdown_markers(content)
    assert len(markers) == len(set(markers))
    assert "judul (#)" in markers
    assert "penegasan tebal (**)" in markers


def test_find_markdown_markers_respects_limit() -> None:
    content = "# Judul\n\nIsi **tebal**.\n\n---\n\n> kutipan\n\n| a | b |"
    assert len(find_markdown_markers(content, limit=2)) == 2
    assert len(find_markdown_markers(content, limit=1)) == 1

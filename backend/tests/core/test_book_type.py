import pytest

from app.core.book_type import (
    BOOK_TYPES,
    DEFAULT_BOOK_TYPE,
    FICTION,
    NON_FICTION,
    UnknownBookTypeError,
    book_type_or_default,
    is_book_type,
    normalize_book_type,
    uses_markdown_content,
)


def test_book_types_cover_both_supported_values() -> None:
    assert BOOK_TYPES == (FICTION, NON_FICTION)


def test_default_book_type_is_fiction() -> None:
    """Proyek lama seluruhnya novel, jadi bawaan tidak boleh berubah tanpa migrasi data."""
    assert DEFAULT_BOOK_TYPE == FICTION


@pytest.mark.parametrize("value", [None, "", "   "])
def test_normalize_book_type_treats_missing_value_as_default(value: str | None) -> None:
    """Formulir HTTP dan baris basis data lama sama-sama dapat memberi nilai tak berisi."""
    assert normalize_book_type(value) == DEFAULT_BOOK_TYPE


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("fiction", FICTION),
        ("non_fiction", NON_FICTION),
        ("  NON_FICTION  ", NON_FICTION),
        ("Fiction", FICTION),
    ],
)
def test_normalize_book_type_accepts_known_values(value: str, expected: str) -> None:
    assert normalize_book_type(value) == expected


@pytest.mark.parametrize("value", ["novel", "nonfiction", "non-fiction", "fiksi"])
def test_normalize_book_type_rejects_unknown_value(value: str) -> None:
    """Nilai tak dikenal ditolak, bukan disenyapkan menjadi bawaan.

    Salah jenis buku berarti isi bab tersimpan dan dibaca dalam format yang berbeda, sehingga
    kegagalan yang terang lebih murah daripada naskah yang tertafsir salah.
    """
    with pytest.raises(UnknownBookTypeError, match="Jenis buku tidak dikenal"):
        normalize_book_type(value)


def test_unknown_book_type_error_lists_supported_values() -> None:
    with pytest.raises(UnknownBookTypeError, match="fiction, non_fiction"):
        normalize_book_type("novel")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("non_fiction", NON_FICTION),
        ("fiction", FICTION),
        ("novel", DEFAULT_BOOK_TYPE),
        ("", DEFAULT_BOOK_TYPE),
        (None, DEFAULT_BOOK_TYPE),
        (123, DEFAULT_BOOK_TYPE),
    ],
)
def test_book_type_or_default_never_raises(value: object, expected: str) -> None:
    """Jalur yang tidak boleh berhenti karena satu kolom rusak memakai pembacaan bertoleransi ini."""
    assert book_type_or_default(value) == expected


def test_is_book_type_distinguishes_known_values() -> None:
    assert is_book_type(FICTION)
    assert is_book_type(NON_FICTION)
    assert not is_book_type("novel")
    assert not is_book_type(None)


def test_uses_markdown_content_only_for_non_fiction() -> None:
    """Fiksi menyimpan prosa polos, sedangkan non-fiksi memikul tabel dan tingkatan judul."""
    assert uses_markdown_content(NON_FICTION)
    assert not uses_markdown_content(FICTION)
    assert not uses_markdown_content(None)


def test_uses_markdown_content_rejects_unknown_value() -> None:
    with pytest.raises(UnknownBookTypeError):
        uses_markdown_content("novel")

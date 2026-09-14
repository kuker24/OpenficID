"""Jenis buku sebuah proyek beserta akibatnya pada format isi bab.

Jenis buku menentukan bentuk kanonik `Chapter.content`, jadi nilainya dibaca lapisan penyimpanan,
API, agen, dan penulis format ekspor. Definisinya diletakkan di `app.core` agar keempat lapisan itu
memakai sumber yang sama tanpa saling mengimpor.

Fiksi menyimpan prosa polos berbasis baris: satu baris adalah satu paragraf, dan penanda markdown
tidak punya arti apa pun di sana. Non-fiksi menyimpan Markdown karena tabel perbandingan, daftar
bernomor, dan tingkatan judul memikul makna yang tidak dapat diwakili prosa datar.
"""

from typing import Literal, get_args


BookType = Literal["fiction", "non_fiction"]

FICTION: BookType = "fiction"
NON_FICTION: BookType = "non_fiction"

BOOK_TYPES: tuple[BookType, ...] = get_args(BookType)

# Proyek yang dibuat sebelum jenis buku ada seluruhnya berupa novel, dan prompt bawaan memang
# melarang markdown pada isi bab. Karena itu fiksi menjadi nilai bawaan, baik bagi baris lama
# maupun bagi permintaan yang tidak menyebutkan jenis buku.
DEFAULT_BOOK_TYPE: BookType = FICTION

# Panjang kolom penyimpanan. Disediakan sebagai konstanta agar model dan migrasi tidak menyimpang.
BOOK_TYPE_MAX_LENGTH = 20


class UnknownBookTypeError(ValueError):
    """Nilai jenis buku berada di luar daftar yang didukung."""


def is_book_type(value: object) -> bool:
    """Memeriksa apakah sebuah nilai merupakan jenis buku yang dikenal."""
    return value in BOOK_TYPES


def normalize_book_type(value: str | None) -> BookType:
    """Menyeragamkan jenis buku yang berasal dari luar proses.

    Formulir HTTP dan baris basis data lama sama-sama dapat memberi nilai kosong, sehingga nilai
    tak berisi diperlakukan sebagai bawaan. Nilai yang berisi namun tidak dikenal sengaja ditolak
    daripada disenyapkan menjadi bawaan, karena salah jenis buku berarti isi bab tersimpan dalam
    format yang salah.
    """
    if value is None:
        return DEFAULT_BOOK_TYPE
    candidate = value.strip().lower()
    if not candidate:
        return DEFAULT_BOOK_TYPE
    # Nilai dicocokkan lewat daftar yang tipenya sudah BookType, sehingga hasilnya terbukti benar
    # bagi pemeriksa tipe tanpa perlu penegasan manual.
    for known in BOOK_TYPES:
        if candidate == known:
            return known
    supported = ", ".join(BOOK_TYPES)
    raise UnknownBookTypeError(
        f"Jenis buku tidak dikenal: {value!r}. Nilai yang didukung: {supported}."
    )


def uses_markdown_content(book_type: str | None) -> bool:
    """Menyatakan apakah isi bab pada jenis buku ini disimpan sebagai Markdown."""
    return normalize_book_type(book_type) == NON_FICTION

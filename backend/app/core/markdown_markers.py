"""Pengenalan penanda Markdown pada isi bab.

Proyek fiksi menyimpan prosa polos berbasis baris, dan prompt bawaan sudah melarang markdown di
sana. Larangan itu tidak pernah ditegakkan di sisi kode, sehingga model yang mengabaikannya
menghasilkan bab berisi `#`, `**`, dan tabel yang tercetak sebagai tanda mentah di penyunting
maupun berkas ekspor.

Pengenalan di sini sengaja dibatasi pada penanda yang hampir tidak mungkin muncul sebagai prosa
sungguhan. Daftar berbutir dan berangka justru tidak diperiksa, karena "- " di awal baris dapat
menjadi tanda pisah dialog dan "1. " dapat menjadi penomoran yang ditulis pengarang. Salah tuduh
akan menolak naskah yang sah, dan itu lebih merugikan daripada satu penanda yang lolos.
"""

from __future__ import annotations

import re


# Setiap pola diberi nama agar pesan galat dapat menunjuk penanda yang sebenarnya ditemukan.
_BLOCK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("judul (#)", re.compile(r"^ {0,3}#{1,6}[ \t]+\S", re.MULTILINE)),
    ("blok kode (```)", re.compile(r"^ {0,3}(?:```|~~~)", re.MULTILINE)),
    ("baris tabel (|)", re.compile(r"^ {0,3}\|.*\|[ \t]*$", re.MULTILINE)),
    ("kutipan blok (>)", re.compile(r"^ {0,3}>[ \t]", re.MULTILINE)),
    ("garis pemisah (---)", re.compile(r"^ {0,3}(?:-{3,}|\*{3,}|_{3,})[ \t]*$", re.MULTILINE)),
)

# Penegasan tebal memerlukan pasangan pada baris yang sama agar tanda bintang tunggal yang berdiri
# sendiri tidak ikut tertangkap.
_INLINE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("penegasan tebal (**)", re.compile(r"\*\*[^*\n]+\*\*")),
)


def find_markdown_markers(content: str, limit: int = 4) -> list[str]:
    """Mengumpulkan nama penanda Markdown yang ditemukan pada isi bab, tanpa duplikat."""
    found: list[str] = []
    for label, pattern in (*_BLOCK_PATTERNS, *_INLINE_PATTERNS):
        if pattern.search(content):
            found.append(label)
            if len(found) >= limit:
                break
    return found


def contains_markdown(content: str) -> bool:
    """Menyatakan apakah isi bab memuat penanda Markdown."""
    return bool(find_markdown_markers(content, limit=1))

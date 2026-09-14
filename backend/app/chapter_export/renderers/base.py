"""Seam bersama bagi setiap penulis format ekspor bab.

Logika pemuatan bertahap, pemeriksaan pembatalan, dan pelaporan kemajuan hanya boleh hidup di
modul ini. Setiap renderer menerima potongan bab yang sudah terurut beserta header volume yang
sudah dihitung, sehingga tidak ada penulis format yang perlu menyentuh basis data atau
menerjemahkan payload tugas sendiri.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, AsyncIterator, Protocol
import unicodedata

from app.background.jobs import service as background_service
from app.chapter_export.markdown_blocks import (
    DocumentBlock,
    HeadingBlock,
    parse_markdown_blocks,
    spans_to_text,
)
from app.core.book_type import book_type_or_default, uses_markdown_content
from app.storage.repos import chapter_repo


EXPORT_BATCH_SIZE = 20


@dataclass(frozen=True)
class RenderedChapter:
    """Satu bab siap tulis beserta header volume yang mendahuluinya bila ada."""

    title: str
    content: str
    volume_heading: str | None
    is_first: bool
    # Terisi hanya bagi proyek non-fiksi. Proyek fiksi menyimpan prosa polos, sehingga penulis
    # format cukup membaca `content` baris demi baris seperti sebelumnya.
    blocks: tuple[DocumentBlock, ...] = ()


class ChapterExportRenderContext(Protocol):
    """Bagian konteks tugas latar belakang yang dipakai penulis format."""

    job_id: str

    async def check_cancelled(self) -> None: ...


def volume_number(value: int) -> str:
    """Mengubah nomor urut volume menjadi label angka untuk judul volume."""
    return str(value)


def volume_export_heading(order: int, title: str) -> str:
    """Menentukan judul volume yang ditulis ke berkas ekspor.

    Judul volume sudah memuat penomorannya sendiri, misalnya "Volume 1" bagi volume bawaan,
    sehingga menambahkan awalan lagi akan menghasilkan "Volume 1 Volume 1". Antarmuka menampilkan
    judul apa adanya, dan ekspor mengikuti perilaku itu. Volume yang judulnya dikosongkan pengguna
    tetap perlu penanda, karena itu nomor urut dipakai sebagai cadangan.
    """
    stripped = title.strip()
    if stripped:
        return stripped
    return f"Volume {volume_number(order)}"


def normalize_chapter_content(value: str) -> str:
    """Menyeragamkan akhir baris agar keluaran tidak bergantung pada asal teksnya."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


# Tanda baca yang lazim berbeda antara judul tersimpan dan judul yang dituliskan model, misalnya
# "Bab 1: Paradoks - Memimpin" berbanding "BAB 1: PARADOKS: MEMIMPIN".
_TITLE_PUNCTUATION = re.compile(r"[:\-\u2013\u2014&.,;'\"()\[\]]+")
_TITLE_SPACES = re.compile(r"\s+")


def _normalize_title_for_comparison(value: str) -> str:
    """Meluruhkan judul menjadi bentuk yang dapat dibandingkan lintas gaya penulisan."""
    folded = unicodedata.normalize("NFKC", value).casefold()
    folded = _TITLE_PUNCTUATION.sub(" ", folded)
    return _TITLE_SPACES.sub(" ", folded).strip()


_ATX_HEADING_LINE = re.compile(r"^#{1,6}[ \t]+(?P<text>.*?)[ \t]*#*[ \t]*$")
_SETEXT_UNDERLINE_LINE = re.compile(r"^(?:=+|-{2,})[ \t]*$")


def strip_duplicate_title_text(content: str, title: str) -> str:
    """Membuang judul markdown pembuka yang hanya mengulang judul bab dari teks mentahnya.

    Rekan fungsi ini di tataran blok melayani penulis format yang merakit dokumen dari AST.
    Penulis TXT menuliskan markdown apa adanya, sehingga tanpa pembuangan di tataran teks judul
    bab akan tampak dua kali: sekali dari medan judul, sekali dari judul markdown pertama.
    """
    lines = content.split("\n")
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return content

    heading = _ATX_HEADING_LINE.match(lines[index].strip())
    consumed = index + 1
    if heading is not None:
        heading_text = heading.group("text")
    elif (
        index + 1 < len(lines)
        and _SETEXT_UNDERLINE_LINE.match(lines[index + 1].strip())
        and lines[index].strip()
    ):
        heading_text = lines[index].strip()
        consumed = index + 2
    else:
        return content

    if _normalize_title_for_comparison(heading_text) != _normalize_title_for_comparison(title):
        return content

    while consumed < len(lines) and not lines[consumed].strip():
        consumed += 1
    return "\n".join(lines[consumed:])


def strip_duplicate_title_heading(
    blocks: tuple[DocumentBlock, ...],
    title: str,
) -> tuple[DocumentBlock, ...]:
    """Membuang judul pembuka yang hanya mengulang judul bab.

    Judul bab sudah tersimpan pada medannya sendiri dan selalu ditulis ulang oleh penulis format,
    sehingga judul markdown pertama yang isinya sama hanya akan tampak sebagai judul ganda. Hanya
    judul di posisi paling awal yang diperiksa, agar judul bagian yang kebetulan bernama serupa di
    tengah naskah tetap terjaga.
    """
    if not blocks:
        return blocks
    first = blocks[0]
    if not isinstance(first, HeadingBlock):
        return blocks
    if _normalize_title_for_comparison(spans_to_text(first.spans)) != (
        _normalize_title_for_comparison(title)
    ):
        return blocks
    return blocks[1:]


async def iter_export_chapters(context, payload: dict[str, Any]) -> AsyncIterator[RenderedChapter]:
    """Memuat isi bab per potongan lalu melaporkan kemajuan setelah tiap potongan tertulis.

    Isi bab sengaja dimuat bertahap agar novel panjang tidak pernah berada di memori seluruhnya.
    Pembatalan diperiksa di batas potongan supaya pembatalan tetap responsif tanpa membelah
    penulisan satu bab.
    """
    chapters = [item for item in payload.get("chapters", []) if isinstance(item, dict)]
    volumes = [item for item in payload.get("volumes", []) if isinstance(item, dict)]
    groups = {
        chapter_id: volume
        for volume in volumes
        for chapter_id in volume.get("chapter_ids", [])
        if isinstance(chapter_id, str)
    }
    mode = payload.get("mode")
    # Jenis buku dibekukan pada payload saat tugas dibuat, sehingga penulis format tidak perlu
    # menyentuh basis data untuk mengetahuinya.
    parse_as_markdown = uses_markdown_content(book_type_or_default(payload.get("book_type")))
    written_count = 0
    last_group_id: str | None = None

    for offset in range(0, len(chapters), EXPORT_BATCH_SIZE):
        await context.check_cancelled()
        batch = chapters[offset : offset + EXPORT_BATCH_SIZE]
        ids = [
            chapter_id
            for chapter_id in (item.get("id") for item in batch)
            if isinstance(chapter_id, str)
        ]
        loaded = await chapter_repo.get_by_ids(context.session, ids)
        loaded_by_id = {chapter.id: chapter for chapter in loaded}
        if len(loaded_by_id) != len(ids):
            raise RuntimeError("Bab yang diekspor sudah dihapus, silakan mulai ekspor ulang")

        for item in batch:
            chapter_id = item.get("id")
            if not isinstance(chapter_id, str):
                raise RuntimeError("Data bab pada tugas ekspor tidak valid")
            chapter = loaded_by_id[chapter_id]
            frozen_title = item.get("title")
            title = frozen_title if isinstance(frozen_title, str) else str(chapter.title or "")
            volume_heading: str | None = None
            if mode == "volumes":
                group = groups.get(chapter_id)
                if not isinstance(group, dict):
                    raise RuntimeError("Data volume pada tugas ekspor tidak valid")
                group_id = group.get("id")
                if not isinstance(group_id, str):
                    raise RuntimeError("Data volume pada tugas ekspor tidak valid")
                if group_id != last_group_id:
                    order = group.get("order")
                    volume_title = group.get("title")
                    if not isinstance(order, int) or not isinstance(volume_title, str):
                        raise RuntimeError("Data volume pada tugas ekspor tidak valid")
                    volume_heading = volume_export_heading(order, volume_title)
                    last_group_id = group_id

            content = normalize_chapter_content(chapter.content)
            blocks: tuple[DocumentBlock, ...] = ()
            if parse_as_markdown:
                blocks = strip_duplicate_title_heading(parse_markdown_blocks(content), title)
                # Penulis TXT menuliskan markdown apa adanya, sehingga judul ganda perlu dibuang
                # dari teksnya juga, bukan hanya dari AST yang dipakai penulis DOCX dan PDF.
                content = strip_duplicate_title_text(content, title)

            yield RenderedChapter(
                title=title,
                content=content,
                volume_heading=volume_heading,
                is_first=written_count == 0,
                blocks=blocks,
            )
            written_count += 1

        last_title = batch[-1].get("title")
        context.job = await background_service.update_progress(
            context.session,
            context.publisher,
            context.job,
            current=written_count,
            total=len(chapters),
            message="writing",
            extra_payload={
                "stage": "writing",
                "chapter_title": last_title if isinstance(last_title, str) else None,
            },
        )
        await context.commit()


async def publish_rendering_stage(context, total: int) -> None:
    """Menandai tahap perakitan berkas agar antarmuka tidak tampak menggantung.

    Format biner merakit seluruh dokumen setelah bab terakhir terbaca, sehingga tanpa penanda ini
    kemajuan akan berhenti di angka terakhir tanpa penjelasan.
    """
    context.job = await background_service.update_progress(
        context.session,
        context.publisher,
        context.job,
        current=total,
        total=total,
        message="rendering",
        extra_payload={"stage": "rendering", "chapter_title": None},
    )
    await context.commit()

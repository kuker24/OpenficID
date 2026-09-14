"""Seam bersama bagi setiap penulis format ekspor bab.

Logika pemuatan bertahap, pemeriksaan pembatalan, dan pelaporan kemajuan hanya boleh hidup di
modul ini. Setiap renderer menerima potongan bab yang sudah terurut beserta header volume yang
sudah dihitung, sehingga tidak ada penulis format yang perlu menyentuh basis data atau
menerjemahkan payload tugas sendiri.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from app.background.jobs import service as background_service
from app.storage.repos import chapter_repo


EXPORT_BATCH_SIZE = 20


@dataclass(frozen=True)
class RenderedChapter:
    """Satu bab siap tulis beserta header volume yang mendahuluinya bila ada."""

    title: str
    content: str
    volume_heading: str | None
    is_first: bool


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

            yield RenderedChapter(
                title=title,
                content=normalize_chapter_content(chapter.content),
                volume_heading=volume_heading,
                is_first=written_count == 0,
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

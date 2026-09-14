"""Logika pemilihan, pengiriman ke penulis format, dan pembersihan tugas ekspor bab."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import re
from typing import Iterable, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.background.jobs import service as background_service
from app.background.jobs.models import BackgroundJob
from app.background.jobs.states import (
    JOB_STATUS_CANCEL_REQUESTED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
)
# Diteruskan kembali karena label volume kini milik penulis format, sementara pemanggil lama
# masih membacanya dari modul layanan ini.
from app.chapter_export.renderers.base import volume_export_heading as volume_export_heading
from app.chapter_export.renderers.base import volume_number as volume_number
from app.chapter_export.renderers.docx import render_docx
from app.chapter_export.renderers.pdf import render_pdf
from app.chapter_export.renderers.txt import render_txt
from app.settings import settings
from app.storage.repos import chapter_repo, project_repo, volume_repo


ExportFormat = Literal["txt", "docx", "pdf"]

EXPORT_JOB_TYPE = "chapter_export"
EXPORT_FILE_PREFIX = "chapter-export-"
EXPORT_FILE_TTL = timedelta(hours=24)
EXPORT_PART_SUFFIX = ".part"
DEFAULT_EXPORT_FORMAT = "txt"
# Setiap format keluaran baru wajib terdaftar pada ketiga peta di bawah. Suffix yang tidak
# terdaftar membuat berkasnya terlewat oleh pembersihan berkala sehingga menumpuk di disk tanpa
# pernah kedaluwarsa, dan media type yang tidak terdaftar membuat unduhan salah tipe.
FORMAT_SUFFIXES: dict[str, str] = {
    "txt": ".txt",
    "docx": ".docx",
    "pdf": ".pdf",
}
FORMAT_MEDIA_TYPES: dict[str, str] = {
    "txt": "text/plain; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}
OUTPUT_SUFFIXES = frozenset(FORMAT_SUFFIXES.values())
MANAGED_SUFFIXES = OUTPUT_SUFFIXES | {EXPORT_PART_SUFFIX}
_RENDERERS = {
    "txt": render_txt,
    "docx": render_docx,
    "pdf": render_pdf,
}


def normalize_export_format(value: object) -> str:
    """Mengembalikan format yang dikenal, memakai TXT untuk tugas lama tanpa medan format."""
    return value if isinstance(value, str) and value in FORMAT_SUFFIXES else DEFAULT_EXPORT_FORMAT


def export_media_type(export_format: str) -> str:
    """Mengambil media type unduhan untuk format ini."""
    return FORMAT_MEDIA_TYPES.get(export_format, FORMAT_MEDIA_TYPES[DEFAULT_EXPORT_FORMAT])


class ChapterExportSelectionError(ValueError):
    """Pilihan ekspor tidak valid."""


@dataclass(frozen=True)
class ExportChapter:
    """Metadata bab yang dibekukan dalam tugas, tanpa memuat isi utama."""

    id: str
    volume_id: str
    title: str
    word_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "volume_id": self.volume_id,
            "title": self.title,
            "word_count": self.word_count,
        }


@dataclass(frozen=True)
class ExportVolume:
    """Judul TXT satu volume utuh beserta bab yang menjadi anggotanya."""

    id: str
    title: str
    order: int
    chapter_ids: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "order": self.order,
            "chapter_ids": self.chapter_ids,
        }


@dataclass(frozen=True)
class ChapterExportPlan:
    """Lingkup ekspor tetap yang diuraikan sebelum tugas latar belakang dibuat."""

    project_id: str
    filename: str
    export_format: str
    mode: str
    chapters: list[ExportChapter]
    volumes: list[ExportVolume]

    @property
    def chapter_ids(self) -> list[str]:
        return [chapter.id for chapter in self.chapters]

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    @property
    def word_count(self) -> int:
        return sum(chapter.word_count for chapter in self.chapters)

    @property
    def volume_count(self) -> int:
        return len(self.volumes) if self.mode == "volumes" else len({chapter.volume_id for chapter in self.chapters})

    def to_payload(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "filename": self.filename,
            "format": self.export_format,
            "mode": self.mode,
            "chapters": [chapter.to_dict() for chapter in self.chapters],
            "volumes": [volume.to_dict() for volume in self.volumes],
            "chapter_count": self.chapter_count,
            "word_count": self.word_count,
            "volume_count": self.volume_count,
        }


def ensure_chapter_exports_dir() -> Path:
    """Memastikan direktori hasil ekspor tersedia."""
    settings.chapter_exports_dir.mkdir(parents=True, exist_ok=True)
    return settings.chapter_exports_dir


def export_file_paths(job_id: str, export_format: str = DEFAULT_EXPORT_FORMAT) -> tuple[Path, Path]:
    """Mengembalikan path berkas sementara dan berkas hasil untuk tugas ini."""
    directory = ensure_chapter_exports_dir()
    basename = f"{EXPORT_FILE_PREFIX}{job_id}"
    suffix = FORMAT_SUFFIXES.get(export_format, FORMAT_SUFFIXES[DEFAULT_EXPORT_FORMAT])
    return directory / f"{basename}{EXPORT_PART_SUFFIX}", directory / f"{basename}{suffix}"


def sanitize_filename_segment(value: str, fallback: str) -> str:
    """Mengubah nama proyek dan volume menjadi potongan nama berkas yang aman lintas platform."""
    normalized = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", " ", value).strip().strip(".")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:120] or fallback


async def create_export_plan(
    session: AsyncSession,
    *,
    project_id: str,
    selected_volume_ids: Iterable[str],
    included_chapter_ids: Iterable[str],
    excluded_chapter_ids: Iterable[str],
    local_date: str,
    export_format: str = DEFAULT_EXPORT_FORMAT,
) -> ChapterExportPlan:
    """Memvalidasi pilihan lalu membekukan lingkup, urutan, dan nama berkas ekspor."""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise LookupError(f"Proyek tidak ditemukan: {project_id}")

    volumes = await volume_repo.list_by_project(session, project_id)
    chapter_metadata = await chapter_repo.list_export_metadata_by_project(session, project_id)
    volume_by_id = {volume.id: volume for volume in volumes}
    chapter_by_id = {
        chapter_id: (volume_id, title, word_count)
        for chapter_id, volume_id, title, word_count in chapter_metadata
    }

    selected_volumes = set(selected_volume_ids)
    included_chapters = set(included_chapter_ids)
    excluded_chapters = set(excluded_chapter_ids)

    unknown_volumes = selected_volumes.difference(volume_by_id)
    unknown_chapters = included_chapters.union(excluded_chapters).difference(chapter_by_id)
    if unknown_volumes or unknown_chapters:
        raise ChapterExportSelectionError(
            "Pilihan ekspor memuat volume atau bab yang bukan milik proyek saat ini"
        )

    selected_ids = {
        chapter_id
        for chapter_id, (volume_id, _title, _word_count) in chapter_by_id.items()
        if volume_id in selected_volumes or chapter_id in included_chapters
    }
    selected_ids.difference_update(excluded_chapters)
    if not selected_ids:
        raise ChapterExportSelectionError("Pilih setidaknya satu bab")

    chapters_by_volume: dict[str, list[tuple[str, str, int]]] = {
        volume.id: [] for volume in volumes
    }
    for chapter_id, (volume_id, title, word_count) in chapter_by_id.items():
        chapters_by_volume.setdefault(volume_id, []).append((chapter_id, title, word_count))

    selected_chapters = [
        (chapter_id, volume_id, title, word_count)
        for chapter_id, (volume_id, title, word_count) in chapter_by_id.items()
        if chapter_id in selected_ids
    ]
    complete_volumes = [
        volume
        for volume in volumes
        if chapters_by_volume[volume.id]
        and all(chapter_id in selected_ids for chapter_id, _title, _word_count in chapters_by_volume[volume.id])
    ]
    # Setiap himpunan pelengkap atau pengecualian bab yang eksplisit menandakan pemilihan bab
    # yang berserakan. Meski hasilnya kebetulan mencakup satu volume penuh, ekspor tetap wajib
    # memakai format bab, dan pemilihan bab pengguna tidak boleh dinaikkan menjadi volume utuh.
    has_fragments = bool(included_chapters or excluded_chapters)
    mode = "chapters" if has_fragments else "volumes"
    nonempty_volumes = [volume for volume in volumes if chapters_by_volume[volume.id]]
    is_full_project = mode == "volumes" and len(complete_volumes) == len(nonempty_volumes)

    project_title = sanitize_filename_segment(project.title, "Proyek Tanpa Nama")
    if is_full_project:
        filename_label = "Lengkap"
    elif mode == "volumes" and len(complete_volumes) == 1:
        filename_label = sanitize_filename_segment(complete_volumes[0].title, "Volume Tanpa Nama")
    elif mode == "volumes":
        filename_label = f"{len(complete_volumes)} Volume"
    else:
        filename_label = f"{len(selected_chapters)} Bab"

    normalized_format = normalize_export_format(export_format)
    suffix = FORMAT_SUFFIXES[normalized_format]
    return ChapterExportPlan(
        project_id=project_id,
        filename=f"{project_title}-{filename_label}-{local_date}{suffix}",
        export_format=normalized_format,
        mode=mode,
        chapters=[
            ExportChapter(
                id=chapter_id,
                volume_id=volume_id,
                title=title or "Bab Tanpa Nama",
                word_count=word_count,
            )
            for chapter_id, volume_id, title, word_count in selected_chapters
        ],
        volumes=[
            ExportVolume(
                id=volume.id,
                title=volume.title or "Volume Tanpa Nama",
                order=volume.order,
                chapter_ids=[chapter_id for chapter_id, _title, _word_count in chapters_by_volume[volume.id]],
            )
            for volume in complete_volumes
        ]
        if mode == "volumes"
        else [],
    )


def get_export_summary(job: BackgroundJob) -> dict[str, object]:
    """Mengambil ringkasan ekspor untuk status frontend dari catatan tugas latar belakang."""
    payload = background_service.parse_json_object(job.payload_json)
    progress = background_service.parse_json_object(job.progress_json)
    result = background_service.parse_json_object(job.result_json)
    error = background_service.parse_json_object(job.error_json)
    expires_at = _parse_datetime(result.get("expires_at"))
    chapter_ids = [
        chapter["id"]
        for chapter in payload.get("chapters", [])
        if isinstance(chapter, dict) and isinstance(chapter.get("id"), str)
    ]
    export_format = normalize_export_format(payload.get("format"))
    return {
        "id": job.id,
        "status": job.status,
        "filename": payload.get("filename", "ekspor-bab.txt"),
        "format": export_format,
        "mode": payload.get("mode", "chapters"),
        "volume_count": int(payload.get("volume_count", 0)),
        "chapter_count": int(payload.get("chapter_count", len(chapter_ids))),
        "word_count": int(payload.get("word_count", 0)),
        "chapter_ids": chapter_ids,
        "current": int(progress.get("current", 0)),
        "total": int(progress.get("total", len(chapter_ids))),
        "stage": progress.get("stage") if isinstance(progress.get("stage"), str) else None,
        "chapter_title": progress.get("chapter_title")
        if isinstance(progress.get("chapter_title"), str)
        else None,
        "expires_at": expires_at,
        "error_message": error.get("message") if isinstance(error.get("message"), str) else None,
    }


async def write_chapter_export(context) -> dict[str, object]:
    """Menulis berkas hasil ekspor memakai penulis yang sesuai format tugas ini.

    Penulisan selalu menuju berkas sementara lalu dipindah secara atomik, sehingga berkas hasil
    tidak pernah terlihat setengah jadi oleh titik akhir unduhan.
    """
    payload = background_service.parse_json_object(context.job.payload_json)
    chapters = [item for item in payload.get("chapters", []) if isinstance(item, dict)]
    if not chapters:
        raise ChapterExportSelectionError("Tugas ekspor tidak memiliki bab yang dapat diproses")

    export_format = normalize_export_format(payload.get("format"))
    part_path, output_path = export_file_paths(context.job_id, export_format)
    renderer = _RENDERERS[export_format]

    try:
        await renderer(context, payload, part_path)
        await context.check_cancelled()
        await asyncio.to_thread(os.replace, part_path, output_path)
        expires_at = datetime.now(UTC) + EXPORT_FILE_TTL
        return {
            "filename": payload.get("filename", "ekspor-bab.txt"),
            "format": export_format,
            "volume_count": payload.get("volume_count", 0),
            "chapter_count": len(chapters),
            "word_count": payload.get("word_count", 0),
            "expires_at": expires_at.isoformat(),
        }
    except BaseException:
        await _delete_export_files(context.job_id)
        raise


async def cleanup_chapter_export_files(session: AsyncSession) -> int:
    """Menghapus berkas ekspor bab yang kedaluwarsa atau sudah tidak dapat dijangkau."""
    directory = ensure_chapter_exports_dir()
    removed = 0
    now = datetime.now(UTC)
    paths = await asyncio.to_thread(lambda: list(directory.iterdir()))
    for path in paths:
        job_id = _job_id_from_export_path(path)
        if job_id is None:
            continue
        job = await background_service.get_job(session, job_id)
        should_keep = False
        if job is not None and job.type == EXPORT_JOB_TYPE:
            # Percabangan wajib memeriksa status lebih dulu. Menyaring berdasarkan suffix lebih dulu
            # membuat cabang masa berlaku tidak pernah terjangkau, sehingga berkas hasil tugas yang
            # sukses tersapu pada sapuan watchdog berikutnya walau umurnya masih jauh dari batas.
            if job.status in {
                JOB_STATUS_PENDING,
                JOB_STATUS_RUNNING,
                JOB_STATUS_CANCEL_REQUESTED,
            }:
                should_keep = True
            elif job.status == JOB_STATUS_SUCCEEDED and path.suffix in OUTPUT_SUFFIXES:
                # Berkas sementara milik tugas sukses adalah sisa rename yang gagal, bukan hasil,
                # sehingga hanya berkas hasil yang berhak bertahan sampai masa berlakunya lewat.
                expires_at = _parse_datetime(
                    background_service.parse_json_object(job.result_json).get("expires_at")
                )
                should_keep = expires_at is not None and expires_at > now
        if should_keep:
            continue
        await asyncio.to_thread(path.unlink, missing_ok=True)
        removed += 1
    return removed


def export_format_of_job(job: BackgroundJob) -> str:
    """Membaca format keluaran yang dibekukan pada payload tugas."""
    payload = background_service.parse_json_object(job.payload_json)
    return normalize_export_format(payload.get("format"))


def is_export_download_available(job: BackgroundJob) -> bool:
    """Memeriksa apakah hasil tugas masih berada dalam masa berlaku unduhan."""
    if job.type != EXPORT_JOB_TYPE or job.status != JOB_STATUS_SUCCEEDED:
        return False
    expires_at = _parse_datetime(background_service.parse_json_object(job.result_json).get("expires_at"))
    if expires_at is None or expires_at <= datetime.now(UTC):
        return False
    _part_path, output_path = export_file_paths(job.id, export_format_of_job(job))
    return output_path.is_file()


async def _delete_export_files(job_id: str) -> None:
    # Hook pembersihan hanya menerima id tugas, tanpa payload yang menyimpan formatnya, sehingga
    # setiap kemungkinan berkas keluaran disapu agar tidak ada sisa saat tugas gagal atau dibatalkan.
    directory = ensure_chapter_exports_dir()
    basename = f"{EXPORT_FILE_PREFIX}{job_id}"
    for suffix in (EXPORT_PART_SUFFIX, *sorted(OUTPUT_SUFFIXES)):
        await asyncio.to_thread((directory / f"{basename}{suffix}").unlink, missing_ok=True)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _job_id_from_export_path(path: Path) -> str | None:
    if path.suffix not in MANAGED_SUFFIXES or not path.name.startswith(EXPORT_FILE_PREFIX):
        return None
    job_id = path.name[len(EXPORT_FILE_PREFIX) : -len(path.suffix)]
    return job_id or None

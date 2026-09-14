# -*- coding: utf-8 -*-
"""
Project Service - lapisan logika bisnis proyek.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.book_type import normalize_book_type
from app.core.errors import ConflictError, NotFoundError
from app.core.storage import delete_cover_file, save_cover_file
from app.storage.models.project import Project
from app.storage.repos import chapter_repo, project_repo, volume_repo
from app.storage.services import task_service, volume_service
from app.storage.services.revision_service import delete_revision_data_by_project


@dataclass
class ProjectListResult:
    """Hasil daftar proyek."""

    items: list[Project]
    total: int
    page: int
    page_size: int


async def is_book_type_locked(session: AsyncSession, project_id: str) -> bool:
    """Menyatakan apakah jenis buku sebuah proyek sudah tidak dapat diubah lagi.

    Jenis buku menentukan format kanonik isi bab, sehingga mengubahnya setelah ada bab akan membuat
    naskah tersimpan dibaca dengan format yang salah. Bab dihitung langsung dari tabelnya, bukan
    dari `Project.chapter_count`, karena kolom itu berupa nilai singgahan yang disegarkan terpisah.
    """
    return await chapter_repo.count_by_project(session, project_id) > 0


async def create_project(
    session: AsyncSession,
    title: str,
    description: str | None = None,
    book_type: str | None = None,
    cover_file: UploadFile | None = None,
) -> Project:
    """
    Membuat proyek.

    Args:
        session: session basis data.
        title: Judul proyek.
        description: Ringkasan proyek, opsional.
        book_type: Jenis buku, opsional. Bila kosong dipakai nilai bawaan.
        cover_file: File sampul, opsional.

    Returns:
        Instance proyek yang dibuat.

    Raises:
        UnknownBookTypeError: Jenis buku berisi namun tidak dikenal.
    """
    project = Project(
        title=title,
        description=description,
        book_type=normalize_book_type(book_type),
    )
    project = await project_repo.create(session, project)
    await volume_service.create_default_volume(session, project.id)

    # Bila file sampul disediakan, simpan sampulnya
    if cover_file:
        cover_path = await save_cover_file(project.id, cover_file)
        project.cover_path = cover_path
        project = await project_repo.update(session, project)

    return project


async def get_project(session: AsyncSession, project_id: str) -> Project:
    """
    Mengambil proyek.

    Args:
        session: session basis data.
        project_id: ID proyek.

    Returns:
        Instance proyek.

    Raises:
        NotFoundError: Proyek tidak ditemukan.
    """
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"Proyek tidak ditemukan: {project_id}")
    return project


async def list_projects(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> ProjectListResult:
    """
    Mengambil daftar proyek.

    Args:
        session: session basis data.
        page: Nomor halaman, mulai dari 1.
        page_size: Jumlah per halaman.
        search: Kata pencarian judul atau ringkasan proyek.
        sort_by: Field pengurutan.
        sort_order: Arah pengurutan.

    Returns:
        Hasil daftar proyek.
    """
    offset = (page - 1) * page_size
    items = await project_repo.list_all(
        session,
        offset=offset,
        limit=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await project_repo.count(session, search=search)
    return ProjectListResult(items=items, total=total, page=page, page_size=page_size)


async def update_project(
    session: AsyncSession,
    project_id: str,
    title: str | None = None,
    description: str | None = None,
    book_type: str | None = None,
    cover_file: UploadFile | None = None,
) -> Project:
    """
    Memperbarui proyek.

    Args:
        session: session basis data.
        project_id: ID proyek.
        title: Judul baru, opsional.
        description: Ringkasan baru, opsional.
        book_type: Jenis buku baru, opsional. Hanya diterima selama proyek belum punya bab.
        cover_file: File sampul baru, opsional.

    Returns:
        Instance proyek setelah diperbarui.

    Raises:
        NotFoundError: Proyek tidak ditemukan.
        ConflictError: Jenis buku diubah padahal proyek sudah memiliki bab.
        UnknownBookTypeError: Jenis buku berisi namun tidak dikenal.
    """
    project = await get_project(session, project_id)

    if title is not None:
        project.title = title
    if description is not None:
        project.description = description
    if book_type is not None:
        requested = normalize_book_type(book_type)
        # Permintaan yang mempertahankan nilai sekarang tidak perlu ditolak, karena formulir sunting
        # mengirim ulang seluruh isinya termasuk jenis buku yang tidak disentuh pengguna.
        if requested != project.book_type:
            if await is_book_type_locked(session, project_id):
                raise ConflictError(
                    "Jenis buku tidak dapat diubah karena proyek sudah memiliki bab. "
                    "Jenis buku menentukan format penyimpanan isi bab."
                )
            project.book_type = requested

    # Bila sampul baru disediakan, ganti sampul yang ada
    if cover_file:
        # Menghapus sampul lama (bila ada)
        if project.cover_path:
            delete_cover_file(project.id)
        # Menyimpan sampul baru
        cover_path = await save_cover_file(project.id, cover_file)
        project.cover_path = cover_path

    project.updated_at = datetime.now(UTC)
    return await project_repo.update(session, project)


async def delete_project(session: AsyncSession, project_id: str) -> None:
    """
    Menghapus proyek.

    Args:
        session: session basis data.
        project_id: ID proyek.

    Raises:
        NotFoundError: Proyek tidak ditemukan.
    """
    project = await get_project(session, project_id)

    await task_service.delete_all_tasks(session, project_id)
    await delete_revision_data_by_project(session, project_id)

    # Membersihkan state indeks retrieval sebelum babnya hilang, karena baris
    # state merujuk chapters.id. Impor dibuat lazy supaya modul ini tidak
    # menarik subsistem retrieval saat hanya dipakai untuk operasi lain.
    from app.retrieval.chapter_index import ChapterIndexIntegrationService

    await ChapterIndexIntegrationService().delete_project_index(session, project_id)

    # Menghapus semua bab dalam proyek
    await chapter_repo.delete_by_project(session, project_id)
    await volume_repo.delete_by_project(session, project_id)

    # Menghapus file sampul (bila ada)
    if project.cover_path:
        delete_cover_file(project.id)

    await project_repo.delete(session, project)

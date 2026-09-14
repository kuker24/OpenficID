"""Penjaga format isi bab menurut jenis buku proyek.

Prompt bawaan melarang markdown pada isi bab proyek fiksi, namun larangan itu tidak pernah
ditegakkan di sisi kode sehingga model yang mengabaikannya tetap berhasil menyimpan bab. Akibatnya
tanda `#` dan `**` tercetak mentah di penyunting maupun berkas ekspor.

Penjaga ini dipakai oleh setiap alat yang menulis isi bab. Menegakkan hanya pada pembuatan bab akan
meninggalkan celah lewat penyuntingan, karena keduanya sama-sama dapat memasukkan markdown.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.tools.errors import ToolExecutionError
from app.core.book_type import UnknownBookTypeError, uses_markdown_content
from app.core.markdown_markers import find_markdown_markers
from app.storage.repos import project_repo


async def guard_chapter_content_format(
    session: AsyncSession,
    project_id: str,
    content: str,
) -> None:
    """Menolak markdown pada isi bab proyek fiksi.

    Proyek non-fiksi dilewati karena markdown justru format kanoniknya. Proyek yang tidak ditemukan
    juga dilewati, sebab kegagalan pencarian proyek bukan urusan penjaga format dan akan dilaporkan
    oleh pemeriksaan lain di alur yang sama.

    Raises:
        ToolExecutionError: Isi bab proyek fiksi memuat penanda markdown.
    """
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        return
    # Nilai jenis buku di luar daftar membuat penjaga melewatkan naskah daripada menolaknya atas
    # dasar nilai yang tidak dapat dipercaya. Menolak penulisan di sini akan menghambat pekerjaan
    # tanpa menjelaskan sebab yang sebenarnya, sedangkan melewatkannya hanya mengembalikan perilaku
    # sebelum penjaga ini ada.
    try:
        if uses_markdown_content(project.book_type):
            return
    except UnknownBookTypeError:
        return

    markers = find_markdown_markers(content)
    if not markers:
        return

    found = ", ".join(markers)
    raise ToolExecutionError(
        f"Proyek ini berjenis fiksi, sehingga isi bab ditulis sebagai prosa polos tanpa markdown. "
        f"Penanda markdown yang ditemukan: {found}. Tulis ulang isi bab tanpa penanda tersebut: "
        f"gunakan paragraf biasa, satu baris untuk satu paragraf. "
        f"Bila naskah ini memang buku non-fiksi, ubah jenis buku pada pengaturan proyek.",
        code="validation_error",
    )

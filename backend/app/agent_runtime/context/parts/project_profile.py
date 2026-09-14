"""Potongan konteks profil proyek: memberi tahu agen jenis buku yang sedang ditulis.

Prompt bawaan menggambarkan penulisan novel dan melarang markdown pada isi bab. Larangan itu benar
bagi fiksi, namun salah bagi naskah non-fiksi yang memikul tabel perbandingan, daftar bernomor, dan
tingkatan judul. Potongan ini yang mengangkat larangan tersebut secara terarah, dan hanya muncul
bagi proyek non-fiksi supaya perilaku fiksi beserta biaya tokennya tidak berubah sama sekali.

Metadata proyek belum pernah mengalir ke prompt sebelum ini, sehingga potongan ini membaca sendiri
entitas proyeknya alih-alih menunggu keadaan runtime membawanya.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.context.errors import ContextBuildError
from app.agent_runtime.context.types import ContextMessage
from app.core.book_type import NON_FICTION, book_type_or_default
from app.storage.repos import project_repo


NON_FICTION_GUIDANCE = """<project_profile>
Proyek ini adalah buku **non-fiksi**, bukan novel.

Ketentuan format isi bab pada profil ini menggantikan ketentuan format bab di prompt di atas:
- Isi bab ditulis dalam Markdown, sehingga larangan markdown pada prompt di atas tidak berlaku.
- Pakai `##` dan `###` untuk subbagian, `**tebal**` untuk penegasan istilah, `*miring*` untuk istilah
  asing, tabel Markdown untuk perbandingan, serta daftar bernomor atau berbutir untuk rincian.
- Jangan menuliskan judul bab sebagai `#` di baris pertama isi. Judul bab sudah tersimpan pada medan
  judulnya sendiri dan akan ditulis ulang oleh berkas ekspor.
- Sertakan rujukan di dalam kalimat bila menyebut penelitian atau sumber.

Ketentuan naratif fiksi tidak berlaku di sini: tidak ada tokoh, dialog, maupun alur cerita. Yang
dituntut adalah ketepatan penalaran, kejelasan struktur, dan keterlacakan sumber.
</project_profile>"""


async def build_project_profile(
    db_session: AsyncSession,
    project_id: str | None = None,
) -> ContextMessage | None:
    """Membangun potongan konteks profil proyek.

    Mengembalikan None bagi proyek fiksi, proyek yang tidak ditemukan, jenis buku yang tidak dapat
    dibaca, dan pemanggilan tanpa project_id, karena prompt bawaan sudah menggambarkan penulisan
    fiksi dengan benar.
    """
    if not project_id:
        return None

    try:
        project = await project_repo.get_by_id(db_session, project_id)
    except Exception as e:
        raise ContextBuildError("project_profile", "failed to load project", cause=e) from e

    if project is None:
        return None

    # Nilai jenis buku di luar daftar tidak boleh menggagalkan pembangunan konteks, sebab itu akan
    # menghentikan seluruh sesi agen hanya karena satu kolom yang tidak dapat dibaca. Penjaga format
    # isi bab mengambil sikap yang sama.
    if book_type_or_default(project.book_type) != NON_FICTION:
        return None

    return ContextMessage(
        role="system",
        content=NON_FICTION_GUIDANCE,
        metadata={"part": "project_profile"},
    )

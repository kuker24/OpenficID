from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.tools.impls.chapter.content_format import guard_chapter_content_format
from app.core.book_type import FICTION, NON_FICTION


MARKDOWN_CONTENT = "# BAB 1: JUDUL\n\nIsi dengan **penegasan** dan tabel.\n\n| a | b |\n| :--- | :--- |"
PLAIN_CONTENT = "Malam turun perlahan.\nAngin membawa bau tanah basah, dan ia tahu belum selesai."


def _project(book_type: str) -> SimpleNamespace:
    return SimpleNamespace(id="proj-1", book_type=book_type)


def _patch_project(project: SimpleNamespace | None):
    return patch(
        "app.agent_runtime.tools.impls.chapter.content_format.project_repo.get_by_id",
        AsyncMock(return_value=project),
    )


@pytest.mark.asyncio
async def test_guard_rejects_markdown_on_fiction_project():
    """Larangan markdown pada prompt fiksi kini ditegakkan di sisi kode, bukan sekadar diminta."""
    session = AsyncMock()
    with _patch_project(_project(FICTION)):
        with pytest.raises(ToolExecutionError) as exc:
            await guard_chapter_content_format(session, "proj-1", MARKDOWN_CONTENT)

    assert exc.value.code == "validation_error"
    message = str(exc.value)
    assert "prosa polos" in message
    assert "judul (#)" in message


@pytest.mark.asyncio
async def test_guard_error_points_to_book_type_setting():
    """Naskah yang sebenarnya non-fiksi perlu diarahkan ke pengaturan, bukan dipaksa ditulis ulang."""
    session = AsyncMock()
    with _patch_project(_project(FICTION)):
        with pytest.raises(ToolExecutionError) as exc:
            await guard_chapter_content_format(session, "proj-1", MARKDOWN_CONTENT)

    assert "jenis buku" in str(exc.value)


@pytest.mark.asyncio
async def test_guard_accepts_plain_prose_on_fiction_project():
    session = AsyncMock()
    with _patch_project(_project(FICTION)):
        await guard_chapter_content_format(session, "proj-1", PLAIN_CONTENT)


@pytest.mark.asyncio
async def test_guard_allows_markdown_on_non_fiction_project():
    """Markdown adalah format kanonik non-fiksi, jadi penjaga tidak boleh menghalanginya."""
    session = AsyncMock()
    with _patch_project(_project(NON_FICTION)):
        await guard_chapter_content_format(session, "proj-1", MARKDOWN_CONTENT)


@pytest.mark.asyncio
async def test_guard_skips_missing_project():
    """Kegagalan pencarian proyek dilaporkan pemeriksaan lain, bukan oleh penjaga format."""
    session = AsyncMock()
    with _patch_project(None):
        await guard_chapter_content_format(session, "hilang", MARKDOWN_CONTENT)


@pytest.mark.asyncio
async def test_guard_skips_unreadable_book_type():
    """Nilai di luar daftar tidak boleh menghambat penulisan atas dasar yang tidak dapat dipercaya."""
    session = AsyncMock()
    with _patch_project(_project("novel")):
        await guard_chapter_content_format(session, "proj-1", MARKDOWN_CONTENT)

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.agent_runtime.context.errors import ContextBuildError
from app.agent_runtime.context.parts.project_profile import build_project_profile
from app.core.book_type import FICTION, NON_FICTION


def _project(book_type: str, project_id: str = "proj-1") -> SimpleNamespace:
    return SimpleNamespace(id=project_id, book_type=book_type)


@pytest.mark.asyncio
async def test_project_profile_returns_none_without_project_id(mock_session):
    """Sesi tanpa proyek tidak punya jenis buku untuk dilaporkan."""
    assert await build_project_profile(mock_session) is None


@pytest.mark.asyncio
async def test_project_profile_returns_none_for_fiction(mock_session):
    """Prompt bawaan sudah menggambarkan penulisan fiksi, jadi tidak ada yang perlu ditambahkan."""
    with patch(
        "app.agent_runtime.context.parts.project_profile.project_repo.get_by_id",
        AsyncMock(return_value=_project(FICTION)),
    ):
        assert await build_project_profile(mock_session, "proj-1") is None


@pytest.mark.asyncio
async def test_project_profile_returns_none_for_missing_project(mock_session):
    """Proyek yang tidak ditemukan bukan urusan potongan konteks ini."""
    with patch(
        "app.agent_runtime.context.parts.project_profile.project_repo.get_by_id",
        AsyncMock(return_value=None),
    ):
        assert await build_project_profile(mock_session, "hilang") is None


@pytest.mark.asyncio
async def test_project_profile_returns_none_for_unreadable_book_type(mock_session):
    """Nilai di luar daftar dilewatkan, karena menolaknya tidak menjelaskan sebab apa pun."""
    with patch(
        "app.agent_runtime.context.parts.project_profile.project_repo.get_by_id",
        AsyncMock(return_value=_project("novel")),
    ):
        assert await build_project_profile(mock_session, "proj-1") is None


@pytest.mark.asyncio
async def test_project_profile_renders_guidance_for_non_fiction(mock_session):
    """Naskah non-fiksi memerlukan pengangkatan larangan markdown secara terarah."""
    with patch(
        "app.agent_runtime.context.parts.project_profile.project_repo.get_by_id",
        AsyncMock(return_value=_project(NON_FICTION)),
    ) as mock_get:
        msg = await build_project_profile(mock_session, "proj-1")

    mock_get.assert_awaited_once_with(mock_session, "proj-1")
    assert msg is not None
    assert msg.role == "system"
    assert msg.metadata == {"part": "project_profile"}
    assert msg.content.startswith("<project_profile>")
    assert msg.content.endswith("</project_profile>")
    assert "non-fiksi" in msg.content
    assert "Markdown" in msg.content


@pytest.mark.asyncio
async def test_project_profile_forbids_repeating_chapter_title_as_heading(mock_session):
    """Judul bab tersimpan pada medannya sendiri, sehingga tidak boleh diulang di dalam isi."""
    with patch(
        "app.agent_runtime.context.parts.project_profile.project_repo.get_by_id",
        AsyncMock(return_value=_project(NON_FICTION)),
    ):
        msg = await build_project_profile(mock_session, "proj-1")

    assert msg is not None
    assert "Jangan menuliskan judul bab" in msg.content


@pytest.mark.asyncio
async def test_project_profile_wraps_repo_errors(mock_session):
    """Kegagalan basis data dilaporkan sebagai galat pembangunan konteks, bukan galat mentah."""
    with patch(
        "app.agent_runtime.context.parts.project_profile.project_repo.get_by_id",
        AsyncMock(side_effect=RuntimeError("basis data mati")),
    ):
        with pytest.raises(ContextBuildError) as exc:
            await build_project_profile(mock_session, "proj-1")

    assert exc.value.part == "project_profile"

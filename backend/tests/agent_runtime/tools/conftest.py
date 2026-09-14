from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.book_type import FICTION


@pytest.fixture(autouse=True)
def _mock_auth_hook_db():
    with patch(
        "app.agent_runtime.tools.hooks.auth._read_user_permissions",
        new=AsyncMock(return_value={}),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_chapter_content_format_project():
    """Menyediakan proyek fiksi bagi penjaga format isi bab.

    Alat bab memakai session tiruan, sehingga pencarian proyek yang sungguhan akan mengembalikan
    coroutine alih-alih entitas. Bawaannya fiksi karena itu jenis buku bawaan sistem; berkas uji
    yang perlu menguji perilaku non-fiksi menimpa tiruan ini sendiri.
    """
    with patch(
        "app.agent_runtime.tools.impls.chapter.content_format.project_repo.get_by_id",
        new=AsyncMock(return_value=SimpleNamespace(id="proj-1", book_type=FICTION)),
    ):
        yield

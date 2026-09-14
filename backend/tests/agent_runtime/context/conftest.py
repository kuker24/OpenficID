from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from app.agent_runtime.graph.state import AgentRuntimeState
from app.core.book_type import FICTION


@pytest.fixture
def mock_session():
    """A mocked AsyncSession that returns AsyncMock for any awaited call."""
    return AsyncMock()


@pytest.fixture(autouse=True)
def _mock_project_profile_project():
    """Menyediakan proyek fiksi bagi potongan konteks profil proyek.

    Pembangunan konteks diuji dengan session tiruan, sehingga pencarian proyek yang sungguhan akan
    mengembalikan coroutine alih-alih entitas. Bawaannya fiksi supaya potongan ini tidak muncul dan
    susunan konteks yang sudah diasersi berkas uji lain tetap utuh. Uji yang memerlukan proyek
    non-fiksi menimpa tiruan ini di dalam badan ujinya sendiri.
    """
    with patch(
        "app.agent_runtime.context.parts.project_profile.project_repo.get_by_id",
        new=AsyncMock(return_value=SimpleNamespace(id="proj_test", book_type=FICTION)),
    ):
        yield


@pytest.fixture
def base_state() -> AgentRuntimeState:
    return {
        "session_id": "sess_test",
        "task_id": "task_test",
        "project_id": "proj_test",
        "model_config": {
            "provider_type": "openai",
            "model_id": "gpt-test",
            "api_key": "k",
            "base_url": "",
            "max_context_tokens": 100_000,
        },
        "active_agent": None,
        "is_completed": False,
        "error": None,
        "retry_count": 0,
        "user_request": "test",
        "current_revision_id": None,
    }


@pytest.fixture
def make_state(base_state):
    def _factory(**overrides: Any) -> AgentRuntimeState:
        merged: dict[str, Any] = {**base_state, **overrides}
        return cast(AgentRuntimeState, merged)
    return _factory

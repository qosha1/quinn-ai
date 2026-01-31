"""Integration tests for SessionPrompter with real database.

Tests the SessionPrompter against a real SQLite database to verify
that the system can retrieve session information and send prompts.
"""

import pytest
from pathlib import Path
from datetime import datetime

from core.db import Database, open_database, init_database
from core.session_prompter import SessionPrompter
from core.queries import (
    create_worker,
    create_team,
    get_worker_continuation_context,
    get_active_session_tmux_name,
)
from core.sessions.persistence import create_session_record


@pytest.fixture
def test_db(tmp_path):
    """Create a test database with schema."""
    db_path = tmp_path / "test.db"
    db = init_database(db_path)
    yield db
    db.close()


@pytest.fixture
def test_org(tmp_path, test_db):
    """Create a test org with team and worker."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()

    # Create team
    team = create_team(
        test_db, name="Test Team", parent_team_id=None, team_id="team-1"
    )

    # Create worker
    worker = create_worker(
        test_db,
        name="Alice",
        role="engineer",
        team_id=team.id,
        cost=50,
        manager_id=None,
        worker_id="worker-123",
    )

    # Create session record
    create_session_record(
        db=test_db,
        session_id="session-123",
        worker_id=worker.id,
        provider="claude_code",
        command="claude",
        args=["code"],
        working_directory=str(org_path),
        tmux_session_name="qn-worker-123",
        state="running",
    )

    return {"org_path": org_path, "team": team, "worker": worker}


class TestSessionPrompterIntegration:
    """Integration tests for SessionPrompter."""

    def test_get_worker_continuation_context(self, test_db, test_org):
        """Test retrieving worker continuation context."""
        worker = test_org["worker"]

        context = get_worker_continuation_context(test_db, worker.id)

        assert context["worker_id"] == worker.id
        assert context["worker_name"] == "Alice"
        assert context["manager_id"] == "ceo"  # No manager set, defaults to ceo
        assert context["team_channel"] == "Test Team"
        assert context["current_task_id"] == "your-task"  # No task set

    def test_get_active_session_tmux_name(self, test_db, test_org):
        """Test retrieving tmux session name for active session."""
        worker = test_org["worker"]

        tmux_name = get_active_session_tmux_name(test_db, worker.id)

        assert tmux_name == "qn-worker-123"

    def test_get_active_session_tmux_name_no_session(self, test_db):
        """Test returns None when no session exists."""
        tmux_name = get_active_session_tmux_name(test_db, "nonexistent-worker")

        assert tmux_name is None

    def test_session_prompter_initialization(self, test_db, test_org):
        """Test SessionPrompter initializes correctly."""
        org_path = test_org["org_path"]

        prompter = SessionPrompter(test_db, org_path)

        assert prompter.db is test_db
        assert prompter.org_path == org_path

    def test_session_prompter_get_session_tmux_name(self, test_db, test_org):
        """Test SessionPrompter can retrieve tmux session name."""
        worker = test_org["worker"]
        prompter = SessionPrompter(test_db, test_org["org_path"])

        tmux_name = prompter._get_session_tmux_name(worker.id)

        assert tmux_name == "qn-worker-123"

    def test_session_prompter_get_worker_context(self, test_db, test_org):
        """Test SessionPrompter can retrieve worker context."""
        worker = test_org["worker"]
        prompter = SessionPrompter(test_db, test_org["org_path"])

        context = prompter._get_worker_context(worker.id)

        assert context["worker_id"] == worker.id
        assert context["worker_name"] == "Alice"
        assert "manager_id" in context
        assert "team_channel" in context
        assert "current_task_id" in context

    def test_prompt_rendering_with_real_context(self, test_db, test_org):
        """Test that prompts render correctly with real database context."""
        from core.constants import CONTINUATION_PROMPT_SOFT_CHECK

        worker = test_org["worker"]
        prompter = SessionPrompter(test_db, test_org["org_path"])

        context = prompter._get_worker_context(worker.id)
        prompt = CONTINUATION_PROMPT_SOFT_CHECK.format(**context)

        # Verify no template placeholders remain
        assert "{worker_id}" not in prompt
        assert "{manager_id}" not in prompt
        assert "{team_channel}" not in prompt
        assert "{current_task_id}" not in prompt

        # Verify real values are present
        assert "your-task" in prompt  # default task id
        assert "ceo" in prompt  # default manager


class TestWorkerWithManager:
    """Test context retrieval with manager set."""

    def test_context_with_manager(self, test_db, test_org):
        """Test context when worker has a manager."""
        # Create manager
        manager = create_worker(
            test_db,
            name="Bob",
            role="manager",
            team_id=test_org["team"].id,
            cost=70,
            worker_id="manager-456",
        )

        # Create worker with manager
        worker = create_worker(
            test_db,
            name="Charlie",
            role="engineer",
            team_id=test_org["team"].id,
            cost=50,
            manager_id=manager.id,
            worker_id="worker-789",
        )

        context = get_worker_continuation_context(test_db, worker.id)

        assert context["manager_id"] == manager.id
        assert context["worker_name"] == "Charlie"

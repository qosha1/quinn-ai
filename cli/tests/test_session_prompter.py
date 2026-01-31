"""Tests for SessionPrompter."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

from core.session_prompter import SessionPrompter
from core.db import Database


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = Mock(spec=Database)
    return db


@pytest.fixture
def org_path(tmp_path):
    """Create a temporary org path."""
    return tmp_path / "test-org"


@pytest.fixture
def session_prompter(mock_db, org_path):
    """Create a SessionPrompter instance."""
    return SessionPrompter(mock_db, org_path)


class TestSessionPrompterInit:
    """Tests for SessionPrompter initialization."""

    def test_init_stores_db_and_path(self, mock_db, org_path):
        """Test that __init__ stores db and org_path."""
        prompter = SessionPrompter(mock_db, org_path)
        assert prompter.db is mock_db
        assert prompter.org_path == org_path


class TestGetSessionTmuxName:
    """Tests for _get_session_tmux_name."""

    @patch("core.session_prompter.get_active_session_tmux_name")
    def test_returns_tmux_name_when_found(
        self, mock_get_tmux, session_prompter, mock_db
    ):
        """Test returns tmux name when session found."""
        mock_get_tmux.return_value = "qn-worker-123"

        result = session_prompter._get_session_tmux_name("worker-123")

        assert result == "qn-worker-123"
        mock_get_tmux.assert_called_once_with(mock_db, "worker-123")

    @patch("core.session_prompter.get_active_session_tmux_name")
    def test_returns_none_when_no_session(
        self, mock_get_tmux, session_prompter, mock_db
    ):
        """Test returns None when no active session."""
        mock_get_tmux.return_value = None

        result = session_prompter._get_session_tmux_name("worker-123")

        assert result is None

    @patch("core.session_prompter.get_active_session_tmux_name")
    def test_handles_exception(self, mock_get_tmux, session_prompter):
        """Test handles exception from query gracefully."""
        mock_get_tmux.side_effect = Exception("DB error")

        result = session_prompter._get_session_tmux_name("worker-123")

        assert result is None


class TestGetWorkerContext:
    """Tests for _get_worker_context."""

    @patch("core.session_prompter.get_worker_continuation_context")
    def test_returns_context_from_query(
        self, mock_get_context, session_prompter, mock_db
    ):
        """Test returns context from query function."""
        expected_context = {
            "worker_id": "worker-123",
            "worker_name": "Alice",
            "manager_id": "manager-456",
            "team_channel": "engineering",
            "current_task_id": "task-789",
        }
        mock_get_context.return_value = expected_context

        result = session_prompter._get_worker_context("worker-123")

        assert result == expected_context
        mock_get_context.assert_called_once_with(mock_db, "worker-123")

    @patch("core.session_prompter.get_worker_continuation_context")
    def test_returns_fallback_on_exception(
        self, mock_get_context, session_prompter
    ):
        """Test returns fallback context on exception."""
        mock_get_context.side_effect = Exception("DB error")

        result = session_prompter._get_worker_context("worker-123")

        assert result["worker_id"] == "worker-123"
        assert result["manager_id"] == "ceo"
        assert result["team_channel"] == "general"
        assert result["current_task_id"] == "your-task"


class TestSendPromptToTmux:
    """Tests for _send_prompt_to_tmux."""

    @patch("subprocess.run")
    def test_sends_prompt_successfully(self, mock_run, session_prompter):
        """Test successfully sends prompt to tmux."""
        mock_run.return_value = MagicMock(returncode=0)
        template = "Hello {worker_name}, task: {current_task_id}"
        context = {"worker_name": "Alice", "current_task_id": "task-123"}

        result = session_prompter._send_prompt_to_tmux(
            "qn-worker-123", template, context
        )

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "tmux"
        assert call_args[1] == "send-keys"
        assert call_args[2] == "-t"
        assert call_args[3] == "qn-worker-123"
        assert "Hello Alice" in call_args[4]
        assert "task-123" in call_args[4]

    @patch("subprocess.run")
    def test_handles_tmux_error(self, mock_run, session_prompter):
        """Test handles tmux command error gracefully."""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, "tmux", stderr="error")

        result = session_prompter._send_prompt_to_tmux(
            "qn-worker-123",
            "Hello {worker_name}",
            {"worker_name": "Alice"},
        )

        assert result is False

    def test_handles_missing_template_key(self, session_prompter):
        """Test handles missing template key gracefully."""
        template = "Hello {worker_name}, task: {missing_key}"
        context = {"worker_name": "Alice"}

        result = session_prompter._send_prompt_to_tmux(
            "qn-worker-123", template, context
        )

        assert result is False


class TestSendSoftCheck:
    """Tests for send_soft_check."""

    @patch("core.session_prompter.get_active_session_tmux_name")
    @patch("core.session_prompter.get_worker_continuation_context")
    @patch("subprocess.run")
    def test_sends_soft_check_successfully(
        self, mock_run, mock_get_context, mock_get_tmux, session_prompter
    ):
        """Test sends soft check prompt successfully."""
        mock_get_tmux.return_value = "qn-worker-123"
        mock_get_context.return_value = {
            "worker_id": "worker-123",
            "worker_name": "Alice",
            "manager_id": "manager-456",
            "team_channel": "engineering",
            "current_task_id": "task-789",
        }
        mock_run.return_value = MagicMock(returncode=0)

        result = session_prompter.send_soft_check("worker-123")

        assert result is True
        mock_run.assert_called_once()
        # Check that soft check prompt was sent
        call_args = mock_run.call_args[0][0]
        assert "ACTIVITY CHECK" in call_args[4]

    @patch("core.session_prompter.get_active_session_tmux_name")
    def test_fails_when_no_tmux_session(
        self, mock_get_tmux, session_prompter
    ):
        """Test fails gracefully when no tmux session."""
        mock_get_tmux.return_value = None

        result = session_prompter.send_soft_check("worker-123")

        assert result is False


class TestSendStatusRequest:
    """Tests for send_status_request."""

    @patch("core.session_prompter.get_active_session_tmux_name")
    @patch("core.session_prompter.get_worker_continuation_context")
    @patch("subprocess.run")
    def test_sends_status_request_successfully(
        self, mock_run, mock_get_context, mock_get_tmux, session_prompter
    ):
        """Test sends status request prompt successfully."""
        mock_get_tmux.return_value = "qn-worker-123"
        mock_get_context.return_value = {
            "worker_id": "worker-123",
            "worker_name": "Alice",
            "manager_id": "manager-456",
            "team_channel": "engineering",
            "current_task_id": "task-789",
        }
        mock_run.return_value = MagicMock(returncode=0)

        result = session_prompter.send_status_request("worker-123")

        assert result is True
        mock_run.assert_called_once()
        # Check that status request prompt was sent
        call_args = mock_run.call_args[0][0]
        assert "STATUS REQUEST" in call_args[4]


class TestSendFinalWarning:
    """Tests for send_final_warning."""

    @patch("core.session_prompter.get_active_session_tmux_name")
    @patch("core.session_prompter.get_worker_continuation_context")
    @patch("subprocess.run")
    def test_sends_final_warning_successfully(
        self, mock_run, mock_get_context, mock_get_tmux, session_prompter
    ):
        """Test sends final warning prompt successfully."""
        mock_get_tmux.return_value = "qn-worker-123"
        mock_get_context.return_value = {
            "worker_id": "worker-123",
            "worker_name": "Alice",
            "manager_id": "manager-456",
            "team_channel": "engineering",
            "current_task_id": "task-789",
        }
        mock_run.return_value = MagicMock(returncode=0)

        result = session_prompter.send_final_warning("worker-123")

        assert result is True
        mock_run.assert_called_once()
        # Check that final warning prompt was sent
        call_args = mock_run.call_args[0][0]
        assert "URGENT" in call_args[4]


class TestPromptRendering:
    """Tests for prompt template rendering."""

    @patch("core.session_prompter.get_active_session_tmux_name")
    @patch("core.session_prompter.get_worker_continuation_context")
    @patch("subprocess.run")
    def test_renders_all_placeholders(
        self, mock_run, mock_get_context, mock_get_tmux, session_prompter
    ):
        """Test that all placeholders in prompts are rendered correctly."""
        mock_get_tmux.return_value = "qn-worker-123"
        mock_get_context.return_value = {
            "worker_id": "worker-123",
            "worker_name": "Alice",
            "manager_id": "manager-456",
            "team_channel": "engineering",
            "current_task_id": "task-789",
        }
        mock_run.return_value = MagicMock(returncode=0)

        session_prompter.send_soft_check("worker-123")

        call_args = mock_run.call_args[0][0]
        prompt = call_args[4]
        # Check that placeholders were replaced
        assert "{current_task_id}" not in prompt
        assert "{manager_id}" not in prompt
        assert "{team_channel}" not in prompt
        assert "task-789" in prompt
        assert "manager-456" in prompt
        assert "engineering" in prompt

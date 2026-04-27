"""Tests verifying OrgCommander uses direct function calls instead of subprocess.

These tests were written TDD-style to specify the desired behavior:
- pause_worker, resume_worker, fire_worker should call cli.core directly
- set_default_provider should write YAML directly
- No subprocess.run() calls for operations that are pure DB or file writes

Tests will FAIL until OrgCommander is refactored to use direct calls.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import yaml

from board_ui.services.org_commander import OrgCommander
from board_ui.interfaces.org_connection import OrgStatus, OrgInfo


# ========================
# Helpers
# ========================


def _make_commander(tmp_path: Path) -> OrgCommander:
    """Create a minimal OrgCommander for testing."""
    db = MagicMock()
    db.fetchone.return_value = None

    org_info = OrgInfo(
        path=tmp_path,
        name="test-org",
        status=OrgStatus.RUNNING,
        ceo_worker_id=None,
        worker_count=1,
        active_session_count=0,
        started_at=None,
        stopped_at=None,
    )

    return OrgCommander(
        db=db,
        org_path=tmp_path,
        board_channel="board-channel",
        escalations_channel="escalations",
        get_ceo_fn=lambda: None,
        get_board_channel_id_fn=lambda: None,
        get_org_info_fn=lambda: org_info,
        mark_message_read_fn=lambda msg_id: None,
    )


# ========================
# pause_worker
# ========================


class TestPauseWorkerDirectCall:
    """pause_worker should call Worker.stop_session() directly, not subprocess."""

    def test_pause_worker_does_not_call_subprocess(self, tmp_path):
        """Verify pause_worker does NOT use subprocess.run."""
        commander = _make_commander(tmp_path)

        mock_worker = MagicMock()

        with (
            patch("subprocess.run") as mock_run,
            patch("board_ui.services.commanders.interventions.Worker.get", return_value=mock_worker),
        ):
            commander.pause_worker("worker-abc", reason="testing")

        mock_run.assert_not_called()

    def test_pause_worker_calls_stop_session(self, tmp_path):
        """Verify pause_worker calls worker.stop_session() directly."""
        commander = _make_commander(tmp_path)

        mock_worker = MagicMock()

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.interventions.Worker.get", return_value=mock_worker),
        ):
            result = commander.pause_worker("worker-abc", reason="testing")

        mock_worker.stop_session.assert_called_once()

    def test_pause_worker_returns_true_on_success(self, tmp_path):
        """pause_worker returns True when stop_session succeeds."""
        commander = _make_commander(tmp_path)
        mock_worker = MagicMock()

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.interventions.Worker.get", return_value=mock_worker),
        ):
            result = commander.pause_worker("worker-abc")

        assert result is True

    def test_pause_worker_returns_false_when_worker_not_found(self, tmp_path):
        """pause_worker returns False when worker doesn't exist."""
        from shared.exceptions import WorkerNotFound

        commander = _make_commander(tmp_path)

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.interventions.Worker.get", side_effect=WorkerNotFound("worker-abc")),
        ):
            result = commander.pause_worker("worker-abc")

        assert result is False


# ========================
# resume_worker
# ========================


class TestResumeWorkerDirectCall:
    """resume_worker should call update_worker_runtime_status() directly, not subprocess."""

    def test_resume_worker_does_not_call_subprocess(self, tmp_path):
        """Verify resume_worker does NOT use subprocess.run."""
        commander = _make_commander(tmp_path)

        with (
            patch("subprocess.run") as mock_run,
            patch("board_ui.services.commanders.interventions.update_worker_runtime_status"),
        ):
            commander.resume_worker("worker-abc")

        mock_run.assert_not_called()

    def test_resume_worker_sets_runtime_to_starting(self, tmp_path):
        """Verify resume_worker calls update_worker_runtime_status with 'starting'."""
        commander = _make_commander(tmp_path)

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.interventions.update_worker_runtime_status") as mock_update,
        ):
            result = commander.resume_worker("worker-abc")

        mock_update.assert_called_once_with(commander._db, "worker-abc", "starting")

    def test_resume_worker_returns_true_on_success(self, tmp_path):
        """resume_worker returns True when update succeeds."""
        commander = _make_commander(tmp_path)

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.interventions.update_worker_runtime_status"),
        ):
            result = commander.resume_worker("worker-abc")

        assert result is True


# ========================
# fire_worker
# ========================


class TestFireWorkerDirectCall:
    """fire_worker should call Worker lifecycle methods directly, not subprocess."""

    def test_fire_worker_does_not_call_subprocess(self, tmp_path):
        """Verify fire_worker does NOT use subprocess.run."""
        commander = _make_commander(tmp_path)
        mock_worker = MagicMock()
        mock_worker.lifecycle_status = "active"

        with (
            patch("subprocess.run") as mock_run,
            patch("board_ui.services.commanders.interventions.Worker", return_value=mock_worker),
        ):
            commander.fire_worker("worker-abc", reason="testing")

        mock_run.assert_not_called()

    def test_fire_worker_calls_lifecycle_methods(self, tmp_path):
        """Verify fire_worker calls start_offboarding() then terminate()."""
        commander = _make_commander(tmp_path)
        mock_worker = MagicMock()
        mock_worker.lifecycle_status = "active"

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.interventions.Worker", return_value=mock_worker),
        ):
            result = commander.fire_worker("worker-abc", reason="testing")

        mock_worker.start_offboarding.assert_called_once()
        mock_worker.terminate.assert_called_once()

    def test_fire_worker_skips_offboarding_if_not_active(self, tmp_path):
        """fire_worker skips start_offboarding if worker is already offboarding."""
        commander = _make_commander(tmp_path)
        mock_worker = MagicMock()
        mock_worker.lifecycle_status = "offboarding"

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.interventions.Worker", return_value=mock_worker),
        ):
            result = commander.fire_worker("worker-abc", reason="testing")

        mock_worker.start_offboarding.assert_not_called()
        mock_worker.terminate.assert_called_once()

    def test_fire_worker_returns_true_on_success(self, tmp_path):
        """fire_worker returns True when lifecycle transitions succeed."""
        commander = _make_commander(tmp_path)
        mock_worker = MagicMock()
        mock_worker.lifecycle_status = "active"

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.interventions.Worker", return_value=mock_worker),
        ):
            result = commander.fire_worker("worker-abc", reason="testing")

        assert result is True


# ========================
# set_default_provider
# ========================


class TestSetDefaultProviderDirectCall:
    """set_default_provider should write YAML directly, not call subprocess."""

    def test_set_default_provider_does_not_call_subprocess(self, tmp_path):
        """Verify set_default_provider does NOT use subprocess.run."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "providers.yaml"
        config_path.write_text("default: claude_code\n")

        commander = _make_commander(tmp_path)

        mock_registry = MagicMock()
        mock_registry.has.return_value = True

        with (
            patch("subprocess.run") as mock_run,
            patch("board_ui.services.commanders.providers.get_default_registry", return_value=mock_registry),
        ):
            commander.set_default_provider("cursor")

        mock_run.assert_not_called()

    def test_set_default_provider_writes_yaml(self, tmp_path):
        """Verify set_default_provider writes the updated default to providers.yaml."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "providers.yaml"
        config_path.write_text("default: claude_code\n")

        commander = _make_commander(tmp_path)

        mock_registry = MagicMock()
        mock_registry.has.return_value = True

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.providers.get_default_registry", return_value=mock_registry),
        ):
            ok, msg = commander.set_default_provider("cursor")

        assert ok is True
        updated = yaml.safe_load(config_path.read_text())
        assert updated["default"] == "cursor"

    def test_set_default_provider_returns_false_for_unknown_provider(self, tmp_path):
        """Returns False when provider is not in registry."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_path = config_dir / "providers.yaml"
        config_path.write_text("default: claude_code\n")

        commander = _make_commander(tmp_path)

        mock_registry = MagicMock()
        mock_registry.has.return_value = False
        mock_registry.list_adapters.return_value = ["claude_code"]

        with (
            patch("subprocess.run"),
            patch("board_ui.services.commanders.providers.get_default_registry", return_value=mock_registry),
        ):
            ok, msg = commander.set_default_provider("unknown_provider")

        assert ok is False
        assert "unknown_provider" in msg

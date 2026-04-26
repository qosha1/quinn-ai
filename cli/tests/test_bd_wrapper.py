"""
Unit tests for beads (bd) wrapper.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cli.core.bd_wrapper import (
    _get_bead_info,
    check_lifecycle_transition,
    get_bundled_bd_path,
    get_org_beads_dir,
    run_bd,
)
from cli.core.lifecycle import (
    CannotCloseBeadError,
    InvalidStateTransitionError,
)


@pytest.fixture
def temp_org():
    """Create temporary org directory with .beads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / ".beads").mkdir()
        yield org_path


class TestGetBundledBdPath:
    """Test bundled bd path resolution."""

    def test_finds_system_bd(self):
        """Should find system bd as fallback."""
        # This test assumes bd is installed on the system
        try:
            bd_path = get_bundled_bd_path()
            assert bd_path.exists()
        except FileNotFoundError:
            pytest.skip("No bd binary available")

    def test_raises_when_not_found(self, monkeypatch):
        """Should raise FileNotFoundError when no bd available."""
        # Mock shutil.which to return None
        monkeypatch.setattr("shutil.which", lambda x: None)

        # Ensure bundled path doesn't exist
        with pytest.raises(FileNotFoundError) as exc:
            # Create a mock that makes the bundled path not exist
            with patch.object(Path, "exists", return_value=False):
                get_bundled_bd_path()

        assert "Beads binary not found" in str(exc.value)


class TestGetOrgBeadsDir:
    """Test org beads directory resolution."""

    def test_returns_beads_subdir(self):
        """Should return .beads subdirectory of org path."""
        org_path = Path("/some/org")
        beads_dir = get_org_beads_dir(org_path)
        assert beads_dir == Path("/some/org/.beads")


class TestRunBd:
    """Test running bd command."""

    def test_requires_org_path(self, monkeypatch):
        """Should require org_path as explicit argument (no env var fallback).

        Follows "No Config Discovery" principle - configuration must be
        passed explicitly at startup, not discovered via environment.
        """
        monkeypatch.delenv("QUINN_ORG_PATH", raising=False)

        # org_path is now a required positional argument
        with pytest.raises(TypeError) as exc:
            run_bd(["list"])

        assert "org_path" in str(exc.value)

    def test_sets_beads_dir(self, temp_org):
        """Should set BEADS_DIR to org's .beads directory."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_bd(["list"], org_path=temp_org)

            call_env = mock_run.call_args.kwargs["env"]
            assert call_env["BEADS_DIR"] == str(temp_org / ".beads")

    def test_sets_worker_context(self, temp_org):
        """Should set worker context when worker_id is provided explicitly."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_bd(["list"], org_path=temp_org, worker_id="worker-123")

            call_env = mock_run.call_args.kwargs["env"]
            assert call_env["QUINN_WORKER_ID"] == "worker-123"
            assert call_env["BEADS_ASSIGNEE"] == "worker-123"

    def test_passes_args_to_bd(self, temp_org):
        """Should pass all arguments to bd command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_bd(["create", "--title", "Test", "--type", "task"], org_path=temp_org)

            # Get the command that was run
            cmd = mock_run.call_args.args[0]
            # Command includes bd path, --sandbox, --db=..., then our args
            # Check that our args are at the end of the command
            user_args = ["create", "--title", "Test", "--type", "task"]
            assert cmd[-len(user_args):] == user_args

    def test_capture_output(self, temp_org):
        """Should capture output when requested."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr="",
            )

            result = run_bd(["list"], org_path=temp_org, capture_output=True)

            assert mock_run.call_args.kwargs["capture_output"] is True
            assert mock_run.call_args.kwargs["text"] is True

    def test_returns_completed_process(self, temp_org):
        """Should return CompletedProcess result."""
        with patch("subprocess.run") as mock_run:
            expected = MagicMock(returncode=0)
            mock_run.return_value = expected

            result = run_bd(["list"], org_path=temp_org)

            assert result is expected


class TestWorkerIdOverride:
    """Test worker ID override behavior."""

    def test_explicit_worker_id(self, temp_org, monkeypatch):
        """Should use explicit worker_id over environment."""
        monkeypatch.setenv("QUINN_WORKER_ID", "env-worker")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_bd(["list"], org_path=temp_org, worker_id="explicit-worker")

            call_env = mock_run.call_args.kwargs["env"]
            assert call_env["QUINN_WORKER_ID"] == "explicit-worker"
            assert call_env["BEADS_ASSIGNEE"] == "explicit-worker"

    def test_no_worker_id(self, temp_org, monkeypatch):
        """Should not set worker context if no worker ID."""
        monkeypatch.delenv("QUINN_WORKER_ID", raising=False)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_bd(["list"], org_path=temp_org)

            call_env = mock_run.call_args.kwargs["env"]
            assert "BEADS_ASSIGNEE" not in call_env


class TestLifecycleValidation:
    """Test lifecycle state validation in bd_wrapper."""

    def test_check_lifecycle_transition_skipped_for_list(self, temp_org):
        """Should skip lifecycle check for list command."""
        # Should not raise even without mocking bd show
        check_lifecycle_transition(["list"], temp_org)

    def test_check_lifecycle_transition_skipped_for_create(self, temp_org):
        """Should skip lifecycle check for create command."""
        check_lifecycle_transition(["create", "--title", "Test"], temp_org)

    def test_check_lifecycle_transition_skipped_when_flag_set(self, temp_org):
        """Should skip when skip_check=True."""
        # This would fail without skip_check since no bead exists
        check_lifecycle_transition(
            ["update", "bead-123", "--status", "review"],
            temp_org,
            skip_check=True,
        )

    def test_check_lifecycle_transition_skipped_without_bead_id(self, temp_org):
        """Should skip when no bead ID in args."""
        check_lifecycle_transition(["update"], temp_org)

    def test_update_with_invalid_transition_raises(self, temp_org):
        """Should raise InvalidStateTransitionError for invalid state transition."""
        # Mock _get_bead_info to return a task bead in investigation state
        with patch("cli.core.bd_wrapper._get_bead_info") as mock_get_info:
            mock_get_info.return_value = {
                "id": "bead-123",
                "type": "task",
                "status": "investigation",
            }

            # Trying to transition directly to review should fail
            with pytest.raises(InvalidStateTransitionError) as exc:
                check_lifecycle_transition(
                    ["update", "bead-123", "--status", "review"],
                    temp_org,
                )

            assert exc.value.bead_id == "bead-123"
            assert exc.value.current_state == "investigation"
            assert exc.value.target_state == "review"

    def test_update_with_valid_transition_succeeds(self, temp_org):
        """Should allow valid state transitions."""
        with patch("cli.core.bd_wrapper._get_bead_info") as mock_get_info:
            mock_get_info.return_value = {
                "id": "bead-123",
                "type": "task",
                "status": "investigation",
            }

            # Should not raise - planning is valid from investigation
            check_lifecycle_transition(
                ["update", "bead-123", "--status", "planning"],
                temp_org,
            )

    def test_close_in_terminal_state_succeeds(self, temp_org):
        """Should allow closing beads in terminal states."""
        with patch("cli.core.bd_wrapper._get_bead_info") as mock_get_info:
            mock_get_info.return_value = {
                "id": "bead-123",
                "type": "task",
                "status": "done",
            }

            # Should not raise - done is a terminal state
            check_lifecycle_transition(["close", "bead-123"], temp_org)

    def test_close_in_non_terminal_state_raises(self, temp_org):
        """Should raise CannotCloseBeadError for non-terminal states."""
        with patch("cli.core.bd_wrapper._get_bead_info") as mock_get_info:
            mock_get_info.return_value = {
                "id": "bead-123",
                "type": "task",
                "status": "review",
            }

            with pytest.raises(CannotCloseBeadError) as exc:
                check_lifecycle_transition(["close", "bead-123"], temp_org)

            assert exc.value.bead_id == "bead-123"
            assert exc.value.current_state == "review"
            assert "Complete the review" in str(exc.value)

    def test_run_bd_validates_lifecycle_by_default(self, temp_org):
        """Should validate lifecycle transitions by default."""
        with patch("cli.core.bd_wrapper._get_bead_info") as mock_get_info:
            mock_get_info.return_value = {
                "id": "bead-123",
                "type": "task",
                "status": "review",
            }

            # Should raise because close is not allowed in review state
            with pytest.raises(CannotCloseBeadError):
                run_bd(["close", "bead-123"], org_path=temp_org)

    def test_run_bd_skips_lifecycle_when_flag_set(self, temp_org):
        """Should skip lifecycle validation when skip_lifecycle_check=True."""
        with patch("cli.core.bd_wrapper._get_bead_info") as mock_get_info:
            mock_get_info.return_value = {
                "id": "bead-123",
                "type": "task",
                "status": "review",
            }

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                # Should not raise despite being in review state
                run_bd(
                    ["close", "bead-123"],
                    org_path=temp_org,
                    skip_lifecycle_check=True,
                )

    def test_lifecycle_check_handles_bead_not_found(self, temp_org):
        """Should gracefully handle when bead info cannot be retrieved."""
        with patch("cli.core.bd_wrapper._get_bead_info") as mock_get_info:
            mock_get_info.return_value = None

            # Should not raise - let bd handle the error
            check_lifecycle_transition(["close", "bead-123"], temp_org)


class TestGetBeadInfo:
    """Test _get_bead_info helper function."""

    def test_parses_json_output(self, temp_org):
        """Should parse bd show --json output."""
        bead_json = json.dumps({
            "id": "bead-123",
            "type": "task",
            "status": "planning",
            "title": "Test bead",
        })

        with patch("cli.core.bd_wrapper.get_bundled_bd_path") as mock_path:
            mock_path.return_value = Path("/usr/local/bin/bd")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=bead_json,
                )

                result = _get_bead_info("bead-123", temp_org)

                assert result["id"] == "bead-123"
                assert result["type"] == "task"
                assert result["status"] == "planning"

    def test_returns_none_on_error(self, temp_org):
        """Should return None when bd show fails."""
        with patch("cli.core.bd_wrapper.get_bundled_bd_path") as mock_path:
            mock_path.return_value = Path("/usr/local/bin/bd")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="Bead not found",
                )

                result = _get_bead_info("bead-123", temp_org)

                assert result is None

    def test_returns_none_on_invalid_json(self, temp_org):
        """Should return None on invalid JSON output."""
        with patch("cli.core.bd_wrapper.get_bundled_bd_path") as mock_path:
            mock_path.return_value = Path("/usr/local/bin/bd")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="not valid json",
                )

                result = _get_bead_info("bead-123", temp_org)

                assert result is None

    def test_returns_none_when_bd_not_found(self, temp_org):
        """Should return None when bd binary not found."""
        with patch("cli.core.bd_wrapper.get_bundled_bd_path") as mock_path:
            mock_path.side_effect = FileNotFoundError("bd not found")

            result = _get_bead_info("bead-123", temp_org)

            assert result is None

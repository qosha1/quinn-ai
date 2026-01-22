"""
Unit tests for beads (bd) wrapper.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cli.core.bd_wrapper import (
    get_bundled_bd_path,
    get_org_beads_dir,
    run_bd,
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
        """Should raise ValueError if org_path not provided."""
        monkeypatch.delenv("QUINN_ORG_PATH", raising=False)

        with pytest.raises(ValueError) as exc:
            run_bd(["list"])

        assert "org_path not provided" in str(exc.value)

    def test_uses_env_org_path(self, temp_org, monkeypatch):
        """Should use QUINN_ORG_PATH from environment."""
        monkeypatch.setenv("QUINN_ORG_PATH", str(temp_org))

        # Mock subprocess.run to avoid actually running bd
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_bd(["list"])

            # Verify BEADS_DIR was set correctly
            call_env = mock_run.call_args.kwargs["env"]
            assert call_env["BEADS_DIR"] == str(temp_org / ".beads")

    def test_sets_beads_dir(self, temp_org):
        """Should set BEADS_DIR to org's .beads directory."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_bd(["list"], org_path=temp_org)

            call_env = mock_run.call_args.kwargs["env"]
            assert call_env["BEADS_DIR"] == str(temp_org / ".beads")

    def test_sets_worker_context(self, temp_org, monkeypatch):
        """Should set worker context from QUINN_WORKER_ID."""
        monkeypatch.setenv("QUINN_WORKER_ID", "worker-123")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_bd(["list"], org_path=temp_org)

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
            # First arg is bd binary path, rest are our args
            assert cmd[1:] == ["create", "--title", "Test", "--type", "task"]

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

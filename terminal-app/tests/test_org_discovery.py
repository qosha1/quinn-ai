"""Tests for org discovery and startup.

Tests finding available orgs and starting them from the board.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from board_ui.services import org_discovery
from board_ui.services.org_discovery import (
    OrgInfo,
    OrgConfig,
    StartResult,
    StopResult,
    discover_running_orgs,
    discover_available_orgs,
    get_org_configs,
    start_org,
    stop_org,
    get_org_status,
    refresh_org_info,
    validate_org_path,
)


@pytest.fixture(autouse=True)
def reset_cli_cache():
    """Reset the CLI command cache before each test."""
    org_discovery._qn_command_cache = None
    yield
    org_discovery._qn_command_cache = None


@pytest.fixture
def temp_org_dir():
    """Create a temporary org directory with mock database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org"
        org_path.mkdir()
        live_path = org_path / "live"
        live_path.mkdir()

        # Create mock quinn.db
        db_path = live_path / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE org_state (
                id TEXT PRIMARY KEY,
                status TEXT,
                ceo_worker_id TEXT,
                started_at TEXT,
                stopped_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE workers (
                id TEXT PRIMARY KEY,
                name TEXT,
                role TEXT,
                team_id TEXT,
                manager_id TEXT,
                status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                worker_id TEXT,
                state TEXT,
                tmux_session_name TEXT
            )
        """)
        conn.execute("""
            INSERT INTO org_state (id, status, ceo_worker_id)
            VALUES ('default', 'running', 'worker-ceo')
        """)
        conn.commit()
        conn.close()

        yield org_path


@pytest.fixture
def temp_stopped_org_dir():
    """Create a temporary org directory with stopped status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "stopped-org"
        org_path.mkdir()
        live_path = org_path / "live"
        live_path.mkdir()

        # Create mock quinn.db with stopped status
        db_path = live_path / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE org_state (
                id TEXT PRIMARY KEY,
                status TEXT,
                ceo_worker_id TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE workers (id TEXT PRIMARY KEY)
        """)
        conn.execute("""
            CREATE TABLE sessions (id TEXT PRIMARY KEY, state TEXT)
        """)
        conn.execute("""
            INSERT INTO org_state (id, status, ceo_worker_id)
            VALUES ('default', 'stopped', 'worker-ceo')
        """)
        conn.commit()
        conn.close()

        yield org_path


@pytest.fixture
def temp_config_dir():
    """Create a temporary org directory with config only (uninitialized)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "uninit-org"
        org_path.mkdir()
        config_path = org_path / "config"
        config_path.mkdir()

        # Create providers.yaml
        providers_yaml = config_path / "providers.yaml"
        providers_yaml.write_text("default: claude_code\n")

        yield org_path


class TestOrgDiscovery:
    """Tests for org discovery functionality."""

    def test_discover_running_orgs(self, temp_org_dir):
        """Should find all currently running orgs."""
        result = discover_running_orgs([temp_org_dir.parent])

        assert len(result) == 1
        assert result[0].name == "test-org"
        assert result[0].status == "running"
        assert result[0].is_running is True
        assert result[0].has_db is True

    def test_discover_running_orgs_excludes_stopped(self, temp_stopped_org_dir):
        """Should not include stopped orgs in running discovery."""
        result = discover_running_orgs([temp_stopped_org_dir.parent])

        # Stopped orgs should not be in running list
        assert len(result) == 0

    def test_discover_available_orgs_includes_all(self, temp_org_dir, temp_stopped_org_dir):
        """Should find all orgs regardless of status."""
        result = discover_available_orgs([temp_org_dir.parent, temp_stopped_org_dir.parent])

        assert len(result) == 2
        statuses = {org.status for org in result}
        assert "running" in statuses
        assert "stopped" in statuses

    def test_discover_available_configs(self, temp_config_dir):
        """Should find org configs that can be started."""
        result = get_org_configs([temp_config_dir.parent])

        assert len(result) == 1
        assert result[0].name == "uninit-org"
        assert result[0].has_providers is True

    def test_start_org_from_board(self, temp_stopped_org_dir):
        """Board should be able to start an org."""
        # Mock subprocess.run to avoid actually running the CLI
        # Note: subprocess.run is called multiple times:
        # 1. check_cli_available() calls --help
        # 2. _get_qn_command() calls --help (cached after first call)
        # 3. The actual org start command
        with patch("board_ui.services.org_discovery.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Organization started successfully",
                stderr="",
            )

            result = start_org(temp_stopped_org_dir)

            assert result.success is True
            assert "started" in result.message.lower()
            # Verify the actual org start command was called (last call)
            assert mock_run.call_count >= 1
            # Check that at least one call was for org start
            calls = mock_run.call_args_list
            start_calls = [c for c in calls if "org" in str(c) and "start" in str(c)]
            assert len(start_calls) == 1

    def test_stop_org_from_board(self, temp_org_dir):
        """Board should be able to stop an org."""
        # Mock subprocess.run to avoid actually running the CLI
        # Note: subprocess.run is called multiple times for CLI availability check
        with patch("board_ui.services.org_discovery.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Organization stopped successfully",
                stderr="",
            )

            result = stop_org(temp_org_dir)

            assert result.success is True
            assert "stopped" in result.message.lower()
            # Verify the actual org stop command was called
            assert mock_run.call_count >= 1
            # Check that at least one call was for org stop
            calls = mock_run.call_args_list
            stop_calls = [c for c in calls if "org" in str(c) and "stop" in str(c)]
            assert len(stop_calls) == 1

    def test_board_independent_of_org_lifecycle(self):
        """Board can run without any org running."""
        # Discovery should work with empty paths
        result = discover_running_orgs([])
        assert result == []

        # Discovery should handle non-existent paths gracefully
        result = discover_available_orgs([Path("/nonexistent/path")])
        assert result == []

    def test_reconnect_to_running_org(self, temp_org_dir):
        """Board can get status of running org."""
        # First discovery
        orgs1 = discover_running_orgs([temp_org_dir.parent])
        assert len(orgs1) == 1

        # Refresh org info
        refreshed = refresh_org_info(orgs1[0])
        assert refreshed.status == "running"
        assert refreshed.path == orgs1[0].path

    def test_get_org_status(self, temp_org_dir):
        """Should get current org status."""
        info = get_org_status(temp_org_dir)

        assert info.name == "test-org"
        assert info.status == "running"
        assert info.is_running is True

    def test_start_org_handles_timeout(self, temp_stopped_org_dir):
        """Should handle subprocess timeout gracefully."""
        import subprocess

        with patch("board_ui.services.org_discovery.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="qn", timeout=30)

            result = start_org(temp_stopped_org_dir)

            assert result.success is False
            assert "timed out" in result.message.lower()

    def test_stop_org_handles_cli_error(self, temp_org_dir):
        """Should handle CLI errors gracefully."""
        with patch("board_ui.services.org_discovery.subprocess.run") as mock_run:
            # First call(s) for CLI availability check should succeed
            # Last call (actual stop) should fail
            def side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("command", [])
                if "--help" in cmd:
                    # CLI availability check succeeds
                    return MagicMock(returncode=0, stdout="Help text", stderr="")
                else:
                    # Actual stop command fails
                    return MagicMock(
                        returncode=1,
                        stdout="",
                        stderr="Organization not found",
                    )

            mock_run.side_effect = side_effect

            result = stop_org(temp_org_dir)

            assert result.success is False
            assert result.returncode == 1


class TestValidateOrgPath:
    """Tests for org path validation."""

    def test_validate_org_path_with_db(self, temp_org_dir):
        """Should validate org with live/quinn.db."""
        is_valid, error = validate_org_path(temp_org_dir)

        assert is_valid is True
        assert error == ""

    def test_validate_org_path_with_config(self, temp_config_dir):
        """Should validate org with config/ directory."""
        is_valid, error = validate_org_path(temp_config_dir)

        assert is_valid is True
        assert error == ""

    def test_validate_org_path_nonexistent(self):
        """Should fail validation for nonexistent path."""
        is_valid, error = validate_org_path(Path("/nonexistent/org/path"))

        assert is_valid is False
        assert "does not exist" in error

    def test_validate_org_path_not_directory(self):
        """Should fail validation when path is a file, not directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "not-a-dir.txt"
            file_path.write_text("just a file")

            is_valid, error = validate_org_path(file_path)

            assert is_valid is False
            assert "not a directory" in error

    def test_validate_org_path_missing_indicators(self):
        """Should fail validation when missing org indicators."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir) / "empty-dir"
            empty_dir.mkdir()

            is_valid, error = validate_org_path(empty_dir)

            assert is_valid is False
            assert "Not a valid org directory" in error
            assert "live/quinn.db" in error
            assert "config/" in error

    def test_start_org_validates_path_first(self):
        """start_org should fail early with invalid path."""
        result = start_org(Path("/nonexistent/org/path"))

        assert result.success is False
        assert "does not exist" in result.message
        assert result.returncode == -1

    def test_stop_org_validates_path_first(self):
        """stop_org should fail early with invalid path."""
        result = stop_org(Path("/nonexistent/org/path"))

        assert result.success is False
        assert "does not exist" in result.message
        assert result.returncode == -1

    def test_start_org_validates_not_empty_dir(self):
        """start_org should fail for empty directory without org indicators."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir) / "empty-dir"
            empty_dir.mkdir()

            result = start_org(empty_dir)

            assert result.success is False
            assert "Not a valid org directory" in result.message

    def test_stop_org_validates_not_empty_dir(self):
        """stop_org should fail for empty directory without org indicators."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir) / "empty-dir"
            empty_dir.mkdir()

            result = stop_org(empty_dir)

            assert result.success is False
            assert "Not a valid org directory" in result.message

    def test_stop_org_passes_yes_flag(self, temp_org_dir):
        """stop_org must pass --yes to avoid hanging on confirmation prompt.

        Without --yes, qn org stop prompts for confirmation when there are
        active sessions. In a TUI background thread, there's no interactive
        stdin, so the subprocess hangs until timeout or fails.
        """
        with patch("board_ui.services.org_discovery.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Organization stopped successfully",
                stderr="",
            )

            stop_org(temp_org_dir)

            # Find the actual stop command call (not --help check)
            calls = mock_run.call_args_list
            stop_calls = [c for c in calls if "org" in str(c) and "stop" in str(c)]
            assert len(stop_calls) == 1

            stop_cmd_args = stop_calls[0][0][0]  # First positional arg = command list
            assert "--yes" in stop_cmd_args, (
                "stop_org must pass --yes to avoid hanging on confirmation prompt"
            )

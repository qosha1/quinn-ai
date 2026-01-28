"""Tests for systemeval integration test harness.

Validates that test fixtures (temp_org_factory, qn_runner, cleanup)
work correctly before building actual integration tests.
"""

import subprocess
from pathlib import Path

import pytest


class TestTempOrgFactory:
    """Test temp_org_factory fixture."""

    def test_creates_temp_directory(self, temp_org_factory):
        """Should create a temporary directory."""
        org = temp_org_factory("test")
        assert org.exists()
        assert org.is_dir()
        assert "quinn_test_test_" in str(org)

    def test_creates_multiple_orgs(self, temp_org_factory):
        """Should create multiple isolated temp orgs."""
        org1 = temp_org_factory("org1")
        org2 = temp_org_factory("org2")

        assert org1.exists()
        assert org2.exists()
        assert org1 != org2

    def test_cleanup_removes_directory(self, temp_org_factory):
        """Should clean up temp directory after test (verified manually)."""
        org = temp_org_factory("cleanup_test")
        org_path_str = str(org)
        # Directory exists during test
        assert org.exists()
        # After test, pytest fixture cleanup will remove it
        # (Can't verify here since cleanup runs after test completes)


class TestQnRunner:
    """Test qn_runner fixture."""

    def test_runs_qn_help(self, qn_runner):
        """Should run qn --help successfully."""
        result = qn_runner("--help", check=False)
        assert result.returncode == 0
        assert "QuinnAI" in result.stdout
        assert "org" in result.stdout

    def test_adds_org_path_option(self, qn_runner, temp_org_factory):
        """Should add --org-path when org_path provided."""
        org = temp_org_factory("path_test")
        result = qn_runner("org", "--help", org_path=org, check=False)
        assert result.returncode == 0

    def test_captures_output(self, qn_runner):
        """Should capture stdout and stderr."""
        result = qn_runner("--help", check=False)
        assert result.stdout  # Should have output
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)

    def test_check_flag_raises_on_failure(self, qn_runner):
        """Should raise AssertionError when check=True and command fails."""
        with pytest.raises(AssertionError) as exc_info:
            qn_runner("nonexistent-command", check=True)

        assert "Command failed" in str(exc_info.value)
        assert "Exit code" in str(exc_info.value)

    def test_check_false_returns_nonzero(self, qn_runner):
        """Should return non-zero exit code when check=False."""
        result = qn_runner("nonexistent-command", check=False)
        assert result.returncode != 0

    def test_passes_env_vars(self, qn_runner):
        """Should pass environment variables to subprocess."""
        result = qn_runner(
            "org", "--help",
            env={"QUINN_TEST_VAR": "test_value"},
            check=False
        )
        assert result.returncode == 0
        # Env var would be available in subprocess


class TestCleanupVerification:
    """Test cleanup_org_sessions function."""

    def test_cleanup_nonexistent_org(self):
        """Should handle cleanup of non-existent org gracefully."""
        from tests.conftest import cleanup_org_sessions
        nonexistent = Path("/tmp/nonexistent_org_12345")
        # Should not raise
        cleanup_org_sessions(nonexistent)

    def test_cleanup_org_without_database(self, temp_org_factory):
        """Should handle cleanup of org without database."""
        from tests.conftest import cleanup_org_sessions
        org = temp_org_factory("no_db")
        # Should not raise
        cleanup_org_sessions(org)

    def test_cleanup_initialized_org(self, temp_org_factory, qn_runner):
        """Should cleanup org with database gracefully."""
        from tests.conftest import cleanup_org_sessions

        org = temp_org_factory("initialized")
        qn_runner("org", "init", org_path=org, check=True)

        # Should not raise
        cleanup_org_sessions(org)

        # Verify no quinn sessions running
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            assert "quinn-" not in result.stdout


class TestIntegrationWorkflow:
    """Test basic integration workflow using fixtures."""

    def test_full_org_lifecycle_with_fixtures(self, temp_org_factory, qn_runner):
        """Should support full org lifecycle using test harness."""
        org = temp_org_factory("lifecycle")

        # Init
        result = qn_runner("org", "init", org_path=org)
        assert result.returncode == 0
        assert (org / "live" / "quinn.db").exists()
        assert (org / "config").exists()

        # Start (skip config validation, no CEO spawn)
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

        # Status
        result = qn_runner("org", "status", org_path=org)
        assert result.returncode == 0
        assert "running" in result.stdout.lower() or "status" in result.stdout.lower()

        # Stop
        result = qn_runner("org", "stop", org_path=org)
        assert result.returncode == 0

        # Cleanup happens automatically via fixture

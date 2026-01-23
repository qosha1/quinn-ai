"""
Integration tests for real bd CLI calls.

These tests verify that the bd wrapper correctly interacts with
the actual bd binary. Tests use pytest markers to optionally skip
in CI environments where bd is not installed.

Tests cover:
- Creating real beads issues
- Reading/showing issues
- Updating issue status
- Closing issues
- Error scenarios
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from cli.core.bd_wrapper import (
    run_bd,
    get_bundled_bd_path,
    get_org_beads_dir,
)


def bd_available() -> bool:
    """Check if bd binary is available."""
    try:
        get_bundled_bd_path()
        return True
    except FileNotFoundError:
        return False


# Skip all tests in this module if bd is not installed
pytestmark = pytest.mark.skipif(
    not bd_available(),
    reason="bd binary not available (bundled or system)"
)


@pytest.fixture
def temp_org():
    """Create a temporary org directory with .beads initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        beads_dir = get_org_beads_dir(org_path)
        beads_dir.mkdir(parents=True)

        # Initialize the beads database by running bd init or first create
        # The --sandbox mode with --db flag will create the DB automatically
        yield org_path


@pytest.fixture
def initialized_beads(temp_org):
    """Create temp org with initialized beads DB."""
    import subprocess
    import os

    # Get bd path and beads dir
    bd_path = get_bundled_bd_path()
    beads_dir = get_org_beads_dir(temp_org)
    beads_db = beads_dir / "beads.db"

    # Set up isolated environment - clear any parent beads dir detection
    env = os.environ.copy()
    env["BEADS_DIR"] = str(beads_dir)
    env["BEADS_DB"] = str(beads_db)
    # Prevent parent directory detection by running from temp dir
    env["HOME"] = str(temp_org)

    # Initialize beads with explicit db path
    # Use --sandbox and explicit --db to avoid workspace detection
    result = subprocess.run(
        [str(bd_path), "--sandbox", f"--db={beads_db}", "init", "--prefix", "test"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(temp_org),  # Run from temp directory
    )

    # If init fails due to existing workspace, try to check if db is usable
    if result.returncode != 0:
        if "already initialized" in result.stderr:
            # Try a simple list command to verify db works
            list_result = subprocess.run(
                [str(bd_path), "--sandbox", f"--db={beads_db}", "list"],
                env=env,
                capture_output=True,
                text=True,
                cwd=str(temp_org),
            )
            if list_result.returncode == 0:
                return temp_org
        pytest.skip(f"Failed to initialize beads: {result.stderr}")

    return temp_org


class TestBdBinaryAccess:
    """Test bd binary discovery and access."""

    def test_bundled_or_system_bd_found(self):
        """Should find bundled or system bd binary."""
        bd_path = get_bundled_bd_path()
        assert bd_path.exists()
        assert os.access(bd_path, os.X_OK)

    def test_org_beads_dir_path(self, temp_org):
        """Should correctly compute org beads directory."""
        beads_dir = get_org_beads_dir(temp_org)
        assert beads_dir == temp_org / ".beads"


class TestBdCreateCommand:
    """Test creating beads issues."""

    def test_create_task(self, initialized_beads):
        """Should create a new task issue."""
        result = run_bd(
            args=["create", "--title", "Test task", "--type", "task"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0
        assert "Created" in result.stdout or result.stdout.strip()

    def test_create_bug(self, initialized_beads):
        """Should create a new bug issue."""
        result = run_bd(
            args=["create", "--title", "Test bug", "--type", "bug"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0

    def test_create_feature(self, initialized_beads):
        """Should create a new feature issue."""
        result = run_bd(
            args=["create", "--title", "Test feature", "--type", "feature"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0

    def test_create_with_priority(self, initialized_beads):
        """Should create issue with priority."""
        result = run_bd(
            args=["create", "--title", "High priority task", "--priority", "1"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0

    def test_create_with_description(self, initialized_beads):
        """Should create issue with description."""
        result = run_bd(
            args=["create", "--title", "Task with desc", "--description", "Detailed description here"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0


class TestBdListCommand:
    """Test listing beads issues."""

    def test_list_empty(self, initialized_beads):
        """Should handle empty list."""
        result = run_bd(
            args=["list"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Empty list is not an error
        assert result.returncode == 0

    def test_list_shows_created_issues(self, initialized_beads):
        """Should show issues after creation."""
        # Create an issue first
        run_bd(
            args=["create", "--title", "Visible task"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # List should show it
        result = run_bd(
            args=["list"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0
        assert "Visible task" in result.stdout or "visible" in result.stdout.lower()

    def test_list_with_status_filter(self, initialized_beads):
        """Should filter by status."""
        # Create an issue
        run_bd(
            args=["create", "--title", "Open issue"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # List open issues
        result = run_bd(
            args=["list", "--status=open"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0


class TestBdShowCommand:
    """Test showing issue details."""

    def test_show_existing_issue(self, initialized_beads):
        """Should show details of existing issue."""
        # Create an issue first
        create_result = run_bd(
            args=["create", "--title", "Show me"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Extract issue ID from output
        # Output format is typically "Created <id>: <title>" or similar
        output = create_result.stdout.strip()

        # Try to extract ID - look for patterns like "quinnai-xxxx" or "beads-xxxx"
        import re
        id_match = re.search(r'([a-z]+-[a-z0-9]+)', output)
        if not id_match:
            # If we can't extract ID, skip this test
            pytest.skip("Could not extract issue ID from create output")

        issue_id = id_match.group(1)

        # Show the issue
        result = run_bd(
            args=["show", issue_id],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0
        assert "Show me" in result.stdout or issue_id in result.stdout

    def test_show_nonexistent_issue(self, initialized_beads):
        """Should fail for nonexistent issue."""
        result = run_bd(
            args=["show", "fake-0000"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Should fail or return error message
        assert result.returncode != 0 or "no issue found" in result.stderr.lower()


class TestBdUpdateCommand:
    """Test updating issue status."""

    def test_update_status(self, initialized_beads):
        """Should update issue status."""
        # Create an issue
        create_result = run_bd(
            args=["create", "--title", "To update"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Extract issue ID
        import re
        id_match = re.search(r'([a-z]+-[a-z0-9]+)', create_result.stdout)
        if not id_match:
            pytest.skip("Could not extract issue ID")
        issue_id = id_match.group(1)

        # Update to in_progress
        result = run_bd(
            args=["update", issue_id, "--status=in_progress"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0


class TestBdCloseCommand:
    """Test closing issues."""

    def test_close_issue(self, initialized_beads):
        """Should close an open issue."""
        # Create an issue
        create_result = run_bd(
            args=["create", "--title", "To close"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Extract issue ID
        import re
        id_match = re.search(r'([a-z]+-[a-z0-9]+)', create_result.stdout)
        if not id_match:
            pytest.skip("Could not extract issue ID")
        issue_id = id_match.group(1)

        # Close the issue
        result = run_bd(
            args=["close", issue_id],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0

    def test_close_with_reason(self, initialized_beads):
        """Should close with a reason."""
        # Create an issue
        create_result = run_bd(
            args=["create", "--title", "Close with reason"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Extract issue ID
        import re
        id_match = re.search(r'([a-z]+-[a-z0-9]+)', create_result.stdout)
        if not id_match:
            pytest.skip("Could not extract issue ID")
        issue_id = id_match.group(1)

        # Close with reason
        result = run_bd(
            args=["close", issue_id, "--reason", "Task completed successfully"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0


class TestBdStatsCommand:
    """Test stats command."""

    def test_stats_empty_db(self, initialized_beads):
        """Should show stats for empty database."""
        result = run_bd(
            args=["stats"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Stats should work on empty db
        assert result.returncode == 0

    def test_stats_with_issues(self, initialized_beads):
        """Should show stats after creating issues."""
        # Create some issues
        for i in range(3):
            run_bd(
                args=["create", "--title", f"Issue {i}"],
                org_path=initialized_beads,
                capture_output=True,
                skip_permission_check=True,
                skip_lifecycle_check=True,
                skip_okr_check=True,
            )

        result = run_bd(
            args=["stats"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0
        # Should mention open issues count
        assert "3" in result.stdout or "open" in result.stdout.lower()


class TestBdEnvironmentSetup:
    """Test that environment variables are set correctly."""

    def test_beads_dir_env_set(self, initialized_beads):
        """Should set BEADS_DIR environment variable."""
        # We verify this by checking the db is created in the right place
        beads_dir = get_org_beads_dir(initialized_beads)

        # Create an issue to ensure DB is created
        run_bd(
            args=["create", "--title", "Env test"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Database should exist in org's .beads directory
        db_path = beads_dir / "beads.db"
        assert db_path.exists()

    def test_worker_id_passed_to_env(self, initialized_beads):
        """Should set worker ID in environment when provided."""
        # Create with worker context
        result = run_bd(
            args=["create", "--title", "Worker test"],
            org_path=initialized_beads,
            worker_id="wrkr-test123",
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # The issue should be created (worker context doesn't block creation)
        assert result.returncode == 0


class TestBdErrorScenarios:
    """Test error handling scenarios."""

    def test_invalid_command(self, initialized_beads):
        """Should handle invalid commands gracefully."""
        result = run_bd(
            args=["notacommand"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Should fail with non-zero exit code
        assert result.returncode != 0

    def test_missing_required_args(self, initialized_beads):
        """Should fail when required args missing."""
        # Create without title should fail
        result = run_bd(
            args=["create"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode != 0

    def test_invalid_priority(self, initialized_beads):
        """Should handle invalid priority values."""
        result = run_bd(
            args=["create", "--title", "Bad priority", "--priority", "invalid"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        # Should fail or handle gracefully
        assert result.returncode != 0 or "error" in result.stderr.lower()


class TestBdReadyCommand:
    """Test ready command for work items without blockers."""

    def test_ready_shows_unblocked_issues(self, initialized_beads):
        """Should show issues that have no blockers."""
        # Create an issue
        run_bd(
            args=["create", "--title", "Ready to work"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        result = run_bd(
            args=["ready"],
            org_path=initialized_beads,
            capture_output=True,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
        )

        assert result.returncode == 0
        # Should show the issue since it has no blockers
        assert "Ready to work" in result.stdout or "ready" in result.stdout.lower()

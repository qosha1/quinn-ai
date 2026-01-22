"""Integration tests for example_orgs workflows.

These tests verify that the example org scripts work correctly
and document known issues for tracking.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


EXAMPLE_ORGS_DIR = Path(__file__).parent.parent / "example_orgs"
QN_WRAPPER = EXAMPLE_ORGS_DIR / "common" / "qn"


@pytest.fixture
def temp_org_dir():
    """Create a temporary directory for org files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def run_qn(*args, org_path: Path = None) -> subprocess.CompletedProcess:
    """Run the qn CLI wrapper with given arguments."""
    cmd = [str(QN_WRAPPER)]
    if org_path:
        cmd.extend(["--org-path", str(org_path)])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestQnWrapper:
    """Test the qn CLI wrapper exists and works."""

    def test_wrapper_exists(self):
        """The qn wrapper script should exist."""
        assert QN_WRAPPER.exists(), f"Wrapper not found at {QN_WRAPPER}"

    def test_wrapper_is_executable(self):
        """The qn wrapper should be executable."""
        assert os.access(QN_WRAPPER, os.X_OK), f"Wrapper not executable: {QN_WRAPPER}"

    def test_wrapper_shows_help(self):
        """qn --help should show usage."""
        result = run_qn("--help")
        assert result.returncode == 0
        assert "QuinnAI" in result.stdout
        assert "org" in result.stdout
        assert "wrkr" in result.stdout


class TestOrgInit:
    """Test qn org init command."""

    def test_init_creates_folder_structure(self, temp_org_dir):
        """qn org init should create the expected folder structure."""
        result = run_qn("org", "init", org_path=temp_org_dir)

        assert result.returncode == 0, f"Init failed: {result.stderr}"
        assert (temp_org_dir / "config").exists()
        assert (temp_org_dir / "org-chart").exists()
        assert (temp_org_dir / "live").exists()
        assert (temp_org_dir / "live" / "quinn.db").exists()
        assert (temp_org_dir / "storage").exists()

    def test_init_creates_ceo(self, temp_org_dir):
        """qn org init should create a CEO worker."""
        result = run_qn("org", "init", "--ceo-name", "TestCEO", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "Created CEO" in result.stdout
        assert "TestCEO" in result.stdout

    def test_init_twice_fails(self, temp_org_dir):
        """qn org init should fail if already initialized."""
        run_qn("org", "init", org_path=temp_org_dir)
        result = run_qn("org", "init", org_path=temp_org_dir)

        assert result.returncode != 0
        assert "already initialized" in result.stdout.lower() or "already initialized" in result.stderr.lower()


class TestOrgStart:
    """Test qn org start command."""

    def test_start_changes_status_to_running(self, temp_org_dir):
        """qn org start should transition org to running."""
        run_qn("org", "init", org_path=temp_org_dir)
        result = run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "running" in result.stdout.lower()

    def test_start_activates_ceo(self, temp_org_dir):
        """qn org start should activate the CEO worker."""
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)

        result = run_qn("org", "status", org_path=temp_org_dir)
        assert "active" in result.stdout.lower()

    @pytest.mark.xfail(reason="Known issue: quinnai-qi2r - Session not spawned on start")
    def test_start_spawns_ceo_session(self, temp_org_dir):
        """qn org start should spawn a tmux session for CEO.

        BUG: This currently fails because `qn org start` does not
        spawn a tmux session. See quinnai-qi2r.
        """
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)

        result = run_qn("org", "status", org_path=temp_org_dir)
        # Should show at least 1 session
        assert "Sessions: 1" in result.stdout or "Sessions:  1" in result.stdout


class TestOrgStatus:
    """Test qn org status command."""

    def test_status_shows_org_info(self, temp_org_dir):
        """qn org status should show org info."""
        run_qn("org", "init", org_path=temp_org_dir)

        result = run_qn("org", "status", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "Status:" in result.stdout
        assert "Workers:" in result.stdout


class TestOrgStop:
    """Test qn org stop command."""

    def test_stop_changes_status_to_stopped(self, temp_org_dir):
        """qn org stop should transition org to stopped."""
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)
        result = run_qn("org", "stop", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()


class TestHelloWorldExample:
    """Test the hello-world example workflow end-to-end."""

    def test_hello_world_init_and_run(self, temp_org_dir):
        """Test the basic hello-world workflow."""
        # Initialize
        result = run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Start
        result = run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        # Check status
        result = run_qn("org", "status", org_path=temp_org_dir)
        assert result.returncode == 0
        assert "running" in result.stdout.lower()
        assert "Alice" in result.stdout

        # Stop
        result = run_qn("org", "stop", org_path=temp_org_dir)
        assert result.returncode == 0


class TestKnownIssues:
    """Tests that document known issues.

    These tests are expected to fail until the issues are fixed.
    Each test links to a bead tracking the issue.
    """

    @pytest.mark.xfail(reason="quinnai-uekq: No channels created during init")
    def test_init_creates_channels(self, temp_org_dir):
        """qn org init should create default channels.

        BUG: Currently no channels are created. Workers need channels
        to communicate. See quinnai-uekq.
        """
        run_qn("org", "init", org_path=temp_org_dir)

        # Query database for channels
        import sqlite3
        db_path = temp_org_dir / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM channels")
        count = cursor.fetchone()[0]
        conn.close()

        assert count > 0, "Expected at least one channel to be created"

    @pytest.mark.xfail(reason="quinnai-8x29: Org-chart shows stale lifecycle status")
    def test_org_chart_reflects_lifecycle_changes(self, temp_org_dir):
        """Org-chart should update when worker lifecycle changes.

        BUG: After start, org-chart still shows 'pending' even though
        worker is 'active'. See quinnai-8x29.
        """
        import yaml

        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)

        org_chart_path = temp_org_dir / "org-chart" / "current.yaml"
        with open(org_chart_path) as f:
            org_chart = yaml.safe_load(f)

        # Find the CEO in the workers dict
        workers = org_chart.get("workers", {})
        ceo_entry = list(workers.values())[0]

        assert ceo_entry["lifecycle"] == "active", \
            f"Expected 'active', got '{ceo_entry['lifecycle']}'"

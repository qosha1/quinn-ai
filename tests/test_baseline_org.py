"""Baseline org lifecycle integration tests.

Tests the complete org lifecycle using real qn commands:
- org init → creates folder structure, CEO, database
- org start → transitions to running, activates CEO
- org stop → graceful shutdown
- org status → shows accurate state
- Error cases and validation

These tests execute actual qn CLI commands via subprocess to validate
end-to-end workflows in realistic scenarios.
"""

import sqlite3
from pathlib import Path

import pytest


class TestOrgInit:
    """Test qn org init command."""

    def test_init_creates_folder_structure(self, temp_org_factory, qn_runner):
        """Should create expected folder structure."""
        org = temp_org_factory("init_folders")

        result = qn_runner("org", "init", org_path=org)

        assert result.returncode == 0
        assert (org / "config").exists()
        assert (org / "org-chart").exists()
        assert (org / "live").exists()
        assert (org / "live" / "workers").exists()
        assert (org / "storage" / "shared").exists()
        assert (org / "storage" / "workers").exists()

    def test_init_creates_config_files(self, temp_org_factory, qn_runner):
        """Should copy config templates."""
        org = temp_org_factory("init_config")

        result = qn_runner("org", "init", org_path=org)

        assert result.returncode == 0
        assert (org / "config" / "providers.yaml").exists()
        assert (org / "config" / "worker-templates.yaml").exists()

    def test_init_creates_org_chart(self, temp_org_factory, qn_runner):
        """Should create org-chart with CEO."""
        org = temp_org_factory("init_orgchart")

        result = qn_runner("org", "init", org_path=org)

        assert result.returncode == 0
        assert (org / "org-chart" / "current.yaml").exists()

    def test_init_creates_database(self, temp_org_factory, qn_runner):
        """Should create SQLite database."""
        org = temp_org_factory("init_db")

        result = qn_runner("org", "init", org_path=org)

        assert result.returncode == 0
        db_path = org / "live" / "quinn.db"
        assert db_path.exists()

        # Verify database has required tables
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        # Core tables should exist
        assert "org_state" in tables
        assert "workers" in tables
        assert "channels" in tables

    def test_init_creates_ceo(self, temp_org_factory, qn_runner):
        """Should create CEO worker."""
        org = temp_org_factory("init_ceo")

        result = qn_runner("org", "init", "--ceo-name", "TestCEO", org_path=org)

        assert result.returncode == 0
        assert "Created CEO" in result.stdout
        assert "TestCEO" in result.stdout

        # Verify CEO in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name, role FROM workers WHERE role = 'CEO'")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "TestCEO"
        assert row[1] == "CEO"

    def test_init_sets_org_status_initialized(self, temp_org_factory, qn_runner):
        """Should set org status to initialized."""
        org = temp_org_factory("init_status")

        result = qn_runner("org", "init", org_path=org)

        assert result.returncode == 0

        # Verify org status in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM org_state WHERE id = 'default'")
        status = cursor.fetchone()[0]
        conn.close()

        assert status == "initialized"

    def test_init_twice_fails(self, temp_org_factory, qn_runner):
        """Should fail if org already initialized."""
        org = temp_org_factory("init_twice")

        # First init
        qn_runner("org", "init", org_path=org)

        # Second init should fail
        result = qn_runner("org", "init", org_path=org, check=False)

        assert result.returncode != 0
        assert "already initialized" in result.stdout.lower() or "already initialized" in result.stderr.lower()

    def test_init_with_custom_ceo_name(self, temp_org_factory, qn_runner):
        """Should use custom CEO name when provided."""
        org = temp_org_factory("init_custom_name")

        result = qn_runner(
            "org", "init",
            "--ceo-name", "CustomCEO",
            org_path=org
        )

        assert result.returncode == 0
        assert "CustomCEO" in result.stdout


class TestOrgStart:
    """Test qn org start command."""

    def test_start_transitions_to_running(self, temp_org_factory, qn_runner):
        """Should transition org status to running."""
        org = temp_org_factory("start_running")
        qn_runner("org", "init", org_path=org)

        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )

        assert result.returncode == 0
        assert "running" in result.stdout.lower() or "started" in result.stdout.lower()

        # Verify org status in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM org_state WHERE id = 'default'")
        status = cursor.fetchone()[0]
        conn.close()

        assert status == "running"

    def test_start_requires_init(self, temp_org_factory, qn_runner):
        """Should require org to be initialized first."""
        org = temp_org_factory("start_no_init")

        result = qn_runner("org", "start", org_path=org, check=False)

        assert result.returncode != 0
        assert "not initialized" in result.stdout.lower() or "not initialized" in result.stderr.lower() or "Run 'qn org init'" in result.stdout

    def test_start_validates_config(self, temp_org_factory, qn_runner):
        """Should validate provider configuration by default."""
        org = temp_org_factory("start_validate")
        qn_runner("org", "init", org_path=org)

        # Start without skip flag should fail (no API key set)
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            org_path=org,
            check=False
        )

        assert result.returncode != 0
        assert "api_key" in result.stdout.lower() or "api_key" in result.stderr.lower() or "configuration" in result.stdout.lower() or "configuration" in result.stderr.lower()

    def test_start_skip_validation_flag(self, temp_org_factory, qn_runner):
        """Should skip validation when --skip-config-validation provided."""
        org = temp_org_factory("start_skip")
        qn_runner("org", "init", org_path=org)

        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )

        assert result.returncode == 0


class TestOrgStop:
    """Test qn org stop command."""

    def test_stop_transitions_to_stopped(self, temp_org_factory, qn_runner):
        """Should transition org status to stopped."""
        org = temp_org_factory("stop_stopped")
        qn_runner("org", "init", org_path=org)
        qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )

        result = qn_runner("org", "stop", org_path=org)

        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()

        # Verify org status in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM org_state WHERE id = 'default'")
        status = cursor.fetchone()[0]
        conn.close()

        assert status == "stopped"

    def test_stop_requires_init(self, temp_org_factory, qn_runner):
        """Should require org to be initialized."""
        org = temp_org_factory("stop_no_init")

        result = qn_runner("org", "stop", org_path=org, check=False)

        assert result.returncode != 0
        assert "not initialized" in result.stdout.lower() or "not initialized" in result.stderr.lower() or "Run 'qn org init'" in result.stdout


class TestOrgStatus:
    """Test qn org status command."""

    def test_status_shows_initialized_org(self, temp_org_factory, qn_runner):
        """Should show org status after init."""
        org = temp_org_factory("status_init")
        qn_runner("org", "init", org_path=org)

        result = qn_runner("org", "status", org_path=org)

        assert result.returncode == 0
        assert "Status:" in result.stdout or "status" in result.stdout.lower()
        assert "Workers:" in result.stdout or "workers" in result.stdout.lower()

    def test_status_shows_running_org(self, temp_org_factory, qn_runner):
        """Should show running status."""
        org = temp_org_factory("status_running")
        qn_runner("org", "init", org_path=org)
        qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )

        result = qn_runner("org", "status", org_path=org)

        assert result.returncode == 0
        assert "running" in result.stdout.lower()

    def test_status_requires_init(self, temp_org_factory, qn_runner):
        """Should require org to be initialized."""
        org = temp_org_factory("status_no_init")

        result = qn_runner("org", "status", org_path=org, check=False)

        assert result.returncode != 0
        assert "not initialized" in result.stdout.lower() or "not initialized" in result.stderr.lower() or "Run 'qn org init'" in result.stdout


class TestOrgFullLifecycle:
    """Test complete org lifecycle workflows."""

    def test_init_start_stop_workflow(self, temp_org_factory, qn_runner):
        """Should support complete init → start → stop workflow."""
        org = temp_org_factory("full_lifecycle")

        # Init
        result = qn_runner("org", "init", org_path=org)
        assert result.returncode == 0
        assert (org / "live" / "quinn.db").exists()

        # Start
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

        # Check status
        result = qn_runner("org", "status", org_path=org)
        assert result.returncode == 0
        assert "running" in result.stdout.lower()

        # Stop
        result = qn_runner("org", "stop", org_path=org)
        assert result.returncode == 0

        # Check status after stop
        result = qn_runner("org", "status", org_path=org)
        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()

    def test_start_stop_cycle(self, temp_org_factory, qn_runner):
        """Should support start → stop → start cycle."""
        org = temp_org_factory("start_stop_cycle")
        qn_runner("org", "init", org_path=org)

        # First start
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

        # Stop
        result = qn_runner("org", "stop", org_path=org)
        assert result.returncode == 0

        # Second start
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

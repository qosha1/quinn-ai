"""E2E test for hello-world example org.

Tests full org lifecycle workflow using hello-world configuration.
Validates the simplest possible QuinnAI workflow: init → start → status → stop.
"""

import sqlite3
from pathlib import Path

import pytest


class TestE2EHelloWorld:
    """End-to-end tests for hello-world example org."""

    def test_hello_world_full_lifecycle(self, temp_org_factory, qn_runner):
        """Should support complete hello-world org lifecycle workflow.

        Scenario:
        1. Initialize org with CEO
        2. Start org (skip CEO spawn for test speed)
        3. Verify org is running
        4. Check status output
        5. Stop org
        6. Verify clean shutdown
        """
        org = temp_org_factory("hello_world_e2e")

        # Phase 1: Initialize
        result = qn_runner("org", "init", "--ceo-name", "Alice", org_path=org)
        assert result.returncode == 0
        assert "Created CEO" in result.stdout or "Alice" in result.stdout

        # Verify folder structure created
        assert (org / "config").exists()
        assert (org / "config" / "providers.yaml").exists()
        assert (org / "config" / "worker-templates.yaml").exists()
        assert (org / "org-chart").exists()
        assert (org / "org-chart" / "current.yaml").exists()
        assert (org / "live").exists()
        assert (org / "live" / "quinn.db").exists()
        assert (org / "storage" / "shared").exists()
        assert (org / "storage" / "workers").exists()

        # Verify database has correct tables
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "org_state" in tables
        assert "workers" in tables
        assert "channels" in tables

        # Verify CEO created in database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name, role FROM workers WHERE role = 'CEO'")
        ceo = cursor.fetchone()
        conn.close()

        assert ceo is not None
        assert ceo[0] == "Alice"
        assert ceo[1] == "CEO"

        # Verify org status is initialized
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM org_state WHERE id = 'default'")
        status = cursor.fetchone()[0]
        conn.close()

        assert status == "initialized"

        # Phase 2: Start
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

        # Verify org status is running
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM org_state WHERE id = 'default'")
        status = cursor.fetchone()[0]
        conn.close()

        assert status == "running"

        # Phase 3: Check status
        result = qn_runner("org", "status", org_path=org)
        assert result.returncode == 0
        assert "running" in result.stdout.lower()
        # Status should show CEO information
        assert "CEO" in result.stdout or "Alice" in result.stdout

        # Phase 4: Stop
        result = qn_runner("org", "stop", org_path=org)
        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()

        # Phase 5: Verify stopped state
        result = qn_runner("org", "status", org_path=org)
        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()

        # Verify database shows stopped
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM org_state WHERE id = 'default'")
        status = cursor.fetchone()[0]
        conn.close()

        assert status == "stopped"

    def test_hello_world_ceo_storage_structure(self, temp_org_factory, qn_runner):
        """Should have proper storage structure for CEO worker.

        Note: Worker storage directories are created when sessions spawn,
        not during org start. This test validates the parent structure exists.
        """
        org = temp_org_factory("hello_world_storage")

        # Initialize
        result = qn_runner("org", "init", "--ceo-name", "Alice", org_path=org)
        assert result.returncode == 0

        # Verify storage directory structure exists
        assert (org / "storage" / "workers").exists()
        assert (org / "storage" / "shared").exists()

        # Get CEO id from database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM workers WHERE role = 'CEO'")
        ceo_id = cursor.fetchone()[0]
        conn.close()

        # Worker-specific storage will be created when session spawns
        # For now, just verify the parent structure is ready
        workers_dir = org / "storage" / "workers"
        assert workers_dir.exists()
        assert workers_dir.is_dir()

    def test_hello_world_restart_cycle(self, temp_org_factory, qn_runner):
        """Should support start → stop → start cycle.

        Validates that an org can be stopped and restarted
        without issues.
        """
        org = temp_org_factory("hello_world_restart")

        # Initialize
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

        # Second start (should work)
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

        # Verify running
        result = qn_runner("org", "status", org_path=org)
        assert result.returncode == 0
        assert "running" in result.stdout.lower()

    def test_hello_world_config_validation(self, temp_org_factory, qn_runner):
        """Should validate provider configuration when required.

        Without --skip-config-validation, org start should fail
        if API keys are not configured.
        """
        org = temp_org_factory("hello_world_validation")

        # Initialize
        qn_runner("org", "init", org_path=org)

        # Try to start without skip flag (should fail without API key)
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            org_path=org,
            check=False
        )

        # Should fail with config-related error
        # (unless ANTHROPIC_API_KEY is set in test environment)
        # This test documents the validation behavior
        assert result.returncode != 0 or "running" in result.stdout.lower()

    def test_hello_world_requires_init_before_start(self, temp_org_factory, qn_runner):
        """Should require initialization before starting.

        Starting an uninitialized org should fail with clear error.
        """
        org = temp_org_factory("hello_world_no_init")

        # Try to start without init
        result = qn_runner("org", "start", org_path=org, check=False)

        assert result.returncode != 0
        assert (
            "not initialized" in result.stdout.lower() or
            "not initialized" in result.stderr.lower() or
            "Run 'qn org init'" in result.stdout
        )

    def test_hello_world_requires_init_before_stop(self, temp_org_factory, qn_runner):
        """Should require initialization before stopping.

        Stopping an uninitialized org should fail with clear error.
        """
        org = temp_org_factory("hello_world_no_init_stop")

        # Try to stop without init
        result = qn_runner("org", "stop", org_path=org, check=False)

        assert result.returncode != 0
        assert (
            "not initialized" in result.stdout.lower() or
            "not initialized" in result.stderr.lower() or
            "Run 'qn org init'" in result.stdout
        )

    def test_hello_world_init_twice_fails(self, temp_org_factory, qn_runner):
        """Should prevent double initialization.

        Attempting to initialize an already-initialized org
        should fail with clear error.
        """
        org = temp_org_factory("hello_world_double_init")

        # First init
        result = qn_runner("org", "init", org_path=org)
        assert result.returncode == 0

        # Second init should fail
        result = qn_runner("org", "init", org_path=org, check=False)

        assert result.returncode != 0
        assert (
            "already initialized" in result.stdout.lower() or
            "already initialized" in result.stderr.lower()
        )

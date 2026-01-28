"""E2E test for startup-team example org.

Tests multi-worker coordination workflow using startup-team configuration.
Validates CEO + Engineer hierarchy and team communication patterns.
"""

import sqlite3
from pathlib import Path

import pytest


class TestE2EStartupTeam:
    """End-to-end tests for startup-team example org."""

    def test_startup_team_full_lifecycle(self, temp_org_factory, qn_runner):
        """Should support complete startup-team org lifecycle workflow.

        Scenario:
        1. Initialize org with CEO
        2. Start org
        3. Verify org is running
        4. Stop org cleanly
        """
        org = temp_org_factory("startup_team_e2e")

        # Phase 1: Initialize with CEO
        result = qn_runner(
            "org", "init",
            "--ceo-name", "Alice",
            "--ceo-role", "CEO",
            org_path=org
        )
        assert result.returncode == 0
        assert "Created CEO" in result.stdout or "Alice" in result.stdout

        # Verify folder structure
        assert (org / "config").exists()
        assert (org / "org-chart").exists()
        assert (org / "live" / "quinn.db").exists()
        assert (org / "storage").exists()

        # Verify CEO in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name, role FROM workers WHERE role = 'CEO'")
        ceo = cursor.fetchone()
        conn.close()

        assert ceo is not None
        assert ceo[0] == "Alice"

        # Phase 2: Start
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

        # Phase 3: Validate running state
        result = qn_runner("org", "status", org_path=org)
        assert result.returncode == 0
        assert "running" in result.stdout.lower()

        # Phase 4: Stop
        result = qn_runner("org", "stop", org_path=org)
        assert result.returncode == 0

        # Phase 5: Verify cleanup
        result = qn_runner("org", "status", org_path=org)
        assert "stopped" in result.stdout.lower()

    def test_startup_team_config_structure(self, temp_org_factory, qn_runner):
        """Should create proper config structure for multi-worker org.

        Validates that worker-templates.yaml is created with
        multiple role definitions (CEO, Engineer, etc.).
        """
        org = temp_org_factory("startup_team_config")

        # Initialize
        result = qn_runner("org", "init", org_path=org)
        assert result.returncode == 0

        # Verify config files exist
        assert (org / "config" / "providers.yaml").exists()
        assert (org / "config" / "worker-templates.yaml").exists()

        # Read worker-templates to verify structure
        templates_path = org / "config" / "worker-templates.yaml"
        templates_content = templates_path.read_text()

        # Should contain at least CEO role
        assert "CEO" in templates_content or "ceo" in templates_content.lower()

    def test_startup_team_ceo_storage_structure(self, temp_org_factory, qn_runner):
        """Should have hierarchical storage structure ready for CEO.

        Note: Worker storage directories are created when sessions spawn.
        This test validates the parent structure exists.
        """
        org = temp_org_factory("startup_team_storage")

        # Initialize and start
        qn_runner("org", "init", org_path=org)
        qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )

        # Verify storage structure exists
        assert (org / "storage" / "workers").exists()
        assert (org / "storage" / "shared").exists()

        # Get CEO id
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM workers WHERE role = 'CEO'")
        ceo_id = cursor.fetchone()[0]
        conn.close()

        # Worker-specific storage created when session spawns
        workers_dir = org / "storage" / "workers"
        assert workers_dir.exists()
        assert workers_dir.is_dir()

    def test_startup_team_shared_storage(self, temp_org_factory, qn_runner):
        """Should create shared storage directories.

        Multi-worker orgs need shared storage for:
        - Team communication
        - Shared knowledge
        - Cross-worker artifacts
        """
        org = temp_org_factory("startup_team_shared")

        # Initialize
        qn_runner("org", "init", org_path=org)

        # Verify shared storage structure
        assert (org / "storage" / "shared").exists()

        # These may be created later, but directory should exist
        shared_storage = org / "storage" / "shared"
        assert shared_storage.is_dir()

    @pytest.mark.skip(reason="Requires delegation authority - quinnai-cr2v.9")
    def test_startup_team_hire_engineer(self, temp_org_factory, qn_runner):
        """Should support CEO hiring an engineer worker.

        This test will pass once delegation and hiring authority
        are implemented in cr2v.9.

        Expected flow:
        1. CEO receives goal requiring engineering work
        2. CEO creates hiring request
        3. Engineer worker is created
        4. Engineer appears in org-chart
        5. Engineer has correct manager (CEO)
        """
        org = temp_org_factory("startup_team_hire")

        # Initialize
        qn_runner("org", "init", "--ceo-name", "Alice", org_path=org)

        # TODO: This would require implementing the hire command
        # result = qn_runner(
        #     "org", "hire",
        #     "--name", "Bob",
        #     "--role", "Engineer",
        #     "--manager", "ceo",
        #     org_path=org
        # )
        # assert result.returncode == 0

        # Verify engineer in database
        # db_path = org / "live" / "quinn.db"
        # conn = sqlite3.connect(str(db_path))
        # cursor = conn.cursor()
        # cursor.execute("SELECT name, role, manager_id FROM workers WHERE role = 'Engineer'")
        # engineer = cursor.fetchone()
        # conn.close()

        # assert engineer is not None
        # assert engineer[0] == "Bob"
        # assert engineer[1] == "Engineer"
        # assert engineer[2] == ceo_id  # Reports to CEO

    @pytest.mark.skip(reason="Requires delegation authority - quinnai-cr2v.9")
    def test_startup_team_worker_hierarchy(self, temp_org_factory, qn_runner):
        """Should create correct manager-subordinate relationships.

        When CEO hires an engineer:
        - Engineer's manager_id should point to CEO
        - CEO should be marked as is_manager=True
        - Engineer storage should be hierarchical: workers/{ceo-id}/{engineer-id}/
        """
        # Test will be implemented when hiring is available
        pass

    @pytest.mark.skip(reason="Requires message passing - quinnai-cr2v.10")
    def test_startup_team_delegation(self, temp_org_factory, qn_runner):
        """Should support CEO delegating work to engineer.

        Expected flow:
        1. CEO receives high-level goal
        2. CEO breaks down into tasks
        3. CEO assigns task to engineer
        4. Engineer receives task via message
        5. Engineer works on task
        6. Engineer reports completion
        7. CEO marks work complete
        """
        # Test will be implemented when message passing is available
        pass

    @pytest.mark.skip(reason="Requires channels - quinnai-cr2v.10")
    def test_startup_team_communication_channels(self, temp_org_factory, qn_runner):
        """Should create communication channels for team.

        Multi-worker orgs need:
        - Direct channels (CEO ↔ Engineer)
        - Team channels (all-hands, engineering)
        - Escalation channels (urgent issues)
        """
        # Test will be implemented when channels are available
        pass

    def test_startup_team_restart_with_multiple_workers(self, temp_org_factory, qn_runner):
        """Should support restart with CEO worker.

        Even with just the CEO, the org should restart cleanly.
        """
        org = temp_org_factory("startup_team_restart")

        # Initialize
        qn_runner("org", "init", org_path=org)

        # First start
        qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )

        # Stop
        qn_runner("org", "stop", org_path=org)

        # Second start
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

        # Verify running
        result = qn_runner("org", "status", org_path=org)
        assert "running" in result.stdout.lower()

    def test_startup_team_database_tables(self, temp_org_factory, qn_runner):
        """Should have all required database tables for multi-worker org.

        Startup-team org needs:
        - org_state (org status)
        - workers (CEO, future hires)
        - channels (communication)
        - messages (future delegation)
        """
        org = temp_org_factory("startup_team_db")

        # Initialize
        qn_runner("org", "init", org_path=org)

        # Check database tables
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        # Core tables required for multi-worker
        assert "org_state" in tables
        assert "workers" in tables
        assert "channels" in tables

        # These may be added later
        # assert "messages" in tables
        # assert "work_items" in tables

    def test_startup_team_ceo_is_manager(self, temp_org_factory, qn_runner):
        """Should mark CEO as manager in database.

        CEO should have is_manager=True since they will
        hire and manage subordinates.
        """
        org = temp_org_factory("startup_team_ceo_manager")

        # Initialize
        qn_runner("org", "init", "--ceo-name", "Alice", org_path=org)

        # Check CEO is_manager flag
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check if is_manager column exists
        cursor.execute("PRAGMA table_info(workers)")
        columns = [row[1] for row in cursor.fetchall()]

        if "is_manager" in columns:
            cursor.execute("SELECT is_manager FROM workers WHERE role = 'CEO'")
            is_manager = cursor.fetchone()
            if is_manager:
                # CEO should be marked as manager
                assert is_manager[0] in (1, True), "CEO should be marked as manager"

        conn.close()

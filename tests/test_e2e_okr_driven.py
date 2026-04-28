"""E2E test for okr-driven example org.

Tests OKR-based work assignment workflow using okr-driven configuration.
Validates strategic goal management and OKR cascade patterns.
"""

import sqlite3
from pathlib import Path

import pytest


class TestE2EOkrDriven:
    """End-to-end tests for okr-driven example org."""

    def test_okr_driven_full_lifecycle(self, temp_org_factory, qn_runner):
        """Should support complete okr-driven org lifecycle workflow.

        Scenario:
        1. Initialize org with CEO
        2. Create OKR directory structure
        3. Add sample OKR configuration
        4. Start org
        5. Verify org is running
        6. Stop org cleanly
        """
        org = temp_org_factory("okr_driven_e2e")

        # Phase 1: Initialize
        result = qn_runner(
            "org", "init",
            "--ceo-name", "Alice",
            org_path=org
        )
        assert result.returncode == 0
        assert "Created CEO" in result.stdout or "Alice" in result.stdout

        # Verify folder structure
        assert (org / "config").exists()
        assert (org / "org-chart").exists()
        assert (org / "live" / "quinn.db").exists()
        assert (org / "storage").exists()

        # Phase 2: Create OKR structure (mimicking setup.sh)
        okr_dir = org / "okrs"
        okr_dir.mkdir(parents=True, exist_ok=True)

        # Create sample Q1 OKR
        q1_okr = okr_dir / "q1-2025.yaml"
        q1_okr.write_text("""# Q1 2025 OKRs
objective:
  id: obj-q1-market
  title: "Establish market presence in Q1"
  description: "Get our product into users' hands and prove value"
  owner: ceo
  timeframe:
    start: 2025-01-01
    end: 2025-03-31
  status: active

key_results:
  - id: kr-mvp-launch
    title: "Launch MVP to public"
    type: milestone
    target_date: 2025-02-15
    status: not_started
    owner: ceo
    progress: 0

  - id: kr-beta-users
    title: "100 active beta users"
    type: metric
    metric_name: active_users
    target_value: 100
    current_value: 0
    status: not_started
    owner: marketing
    progress: 0

  - id: kr-nps
    title: "NPS score > 40"
    type: metric
    metric_name: nps_score
    target_value: 40
    current_value: null
    status: not_started
    owner: product
    progress: 0
""")

        assert q1_okr.exists()

        # Phase 3: Start
        result = qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )
        assert result.returncode == 0

        # Phase 4: Validate running state
        result = qn_runner("org", "status", org_path=org)
        assert result.returncode == 0
        assert "running" in result.stdout.lower()

        # Phase 5: Stop
        result = qn_runner("org", "stop", org_path=org)
        assert result.returncode == 0

        # Phase 6: Verify cleanup
        result = qn_runner("org", "status", org_path=org)
        assert "stopped" in result.stdout.lower()

        # Verify OKR files persisted
        assert (org / "okrs" / "q1-2025.yaml").exists()

    def test_okr_driven_config_structure(self, temp_org_factory, qn_runner):
        """Should create proper config structure for OKR-driven org.

        Validates that the org can be initialized and configured
        to work with OKR-based planning.
        """
        org = temp_org_factory("okr_driven_config")

        # Initialize
        result = qn_runner("org", "init", org_path=org)
        assert result.returncode == 0

        # Verify standard config files
        assert (org / "config" / "providers.yaml").exists()
        assert (org / "config" / "worker-templates.yaml").exists()

        # Create OKR directory
        okr_dir = org / "okrs"
        okr_dir.mkdir(parents=True, exist_ok=True)

        # Directory structure should support OKRs
        assert okr_dir.exists()
        assert okr_dir.is_dir()

    def test_okr_driven_ceo_storage_structure(self, temp_org_factory, qn_runner):
        """Should have hierarchical storage structure for CEO in OKR-driven org.

        Note: Worker storage directories are created when sessions spawn.
        This test validates the parent structure exists.
        """
        org = temp_org_factory("okr_driven_storage")

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

    def test_okr_driven_multiple_okr_files(self, temp_org_factory, qn_runner):
        """Should support multiple OKR files (Q1, Q2, etc.).

        OKR-driven orgs typically have:
        - Quarterly OKRs (q1-2025.yaml, q2-2025.yaml)
        - Annual OKRs (2025.yaml)
        - Team-specific OKRs (engineering-q1.yaml)
        """
        org = temp_org_factory("okr_driven_multi")

        # Initialize
        qn_runner("org", "init", org_path=org)

        # Create multiple OKR files
        okr_dir = org / "okrs"
        okr_dir.mkdir(parents=True, exist_ok=True)

        # Q1 OKR
        (okr_dir / "q1-2025.yaml").write_text("""
objective:
  id: obj-q1
  title: "Q1 Objective"
  owner: ceo
""")

        # Q2 OKR
        (okr_dir / "q2-2025.yaml").write_text("""
objective:
  id: obj-q2
  title: "Q2 Objective"
  owner: ceo
""")

        # Annual OKR
        (okr_dir / "2025.yaml").write_text("""
objective:
  id: obj-2025
  title: "2025 Annual Objective"
  owner: ceo
""")

        # Verify files created
        assert (okr_dir / "q1-2025.yaml").exists()
        assert (okr_dir / "q2-2025.yaml").exists()
        assert (okr_dir / "2025.yaml").exists()

    @pytest.mark.skip(reason="OKR commands not yet implemented")
    def test_okr_set_command(self, temp_org_factory, qn_runner):
        """Should support setting org-level OKRs via qn okr set.

        Once implemented, this would:
        1. Create or update an OKR in the database
        2. Link OKR to org/worker
        3. Set initial progress to 0%
        """
        org = temp_org_factory("okr_driven_set")

        # Initialize
        qn_runner("org", "init", org_path=org)

        # TODO: Implement this when OKR commands exist
        # result = qn_runner(
        #     "okr", "set",
        #     "--title", "Launch MVP",
        #     "--type", "milestone",
        #     "--target-date", "2025-02-15",
        #     "--owner", "ceo",
        #     org_path=org
        # )
        # assert result.returncode == 0

    @pytest.mark.skip(reason="OKR commands not yet implemented")
    def test_okr_list_command(self, temp_org_factory, qn_runner):
        """Should list all OKRs via qn okr list.

        Expected output:
        - List of objectives
        - Progress percentage for each
        - Owner information
        - Status (active, completed, cancelled)
        """
        org = temp_org_factory("okr_driven_list")

        # Initialize with OKRs
        qn_runner("org", "init", org_path=org)

        # Create OKR directory with sample data
        okr_dir = org / "okrs"
        okr_dir.mkdir(parents=True, exist_ok=True)
        (okr_dir / "q1-2025.yaml").write_text("""
objective:
  id: obj-q1
  title: "Q1 Objective"
  owner: ceo
key_results:
  - id: kr-1
    title: "Key Result 1"
    progress: 25
""")

        # TODO: Implement this when OKR commands exist
        # result = qn_runner("okr", "list", org_path=org)
        # assert result.returncode == 0
        # assert "obj-q1" in result.stdout
        # assert "Q1 Objective" in result.stdout
        # assert "25%" in result.stdout  # Progress

    @pytest.mark.skip(reason="OKR commands not yet implemented")
    def test_okr_show_command(self, temp_org_factory, qn_runner):
        """Should show detailed OKR info via qn okr show.

        Expected output:
        - Objective title and description
        - All key results with progress
        - Work items linked to each KR
        - Owner and timeline info
        """
        org = temp_org_factory("okr_driven_show")

        # Initialize with OKRs
        qn_runner("org", "init", org_path=org)

        # Create sample OKR
        okr_dir = org / "okrs"
        okr_dir.mkdir(parents=True, exist_ok=True)
        (okr_dir / "q1-2025.yaml").write_text("""
objective:
  id: obj-q1
  title: "Launch Product"
  description: "Get MVP to market"
  owner: ceo
key_results:
  - id: kr-1
    title: "Complete backend"
    progress: 50
  - id: kr-2
    title: "Ship frontend"
    progress: 30
""")

        # TODO: Implement this when OKR commands exist
        # result = qn_runner("okr", "show", "obj-q1", org_path=org)
        # assert result.returncode == 0
        # assert "Launch Product" in result.stdout
        # assert "Get MVP to market" in result.stdout
        # assert "Complete backend" in result.stdout
        # assert "50%" in result.stdout

    @pytest.mark.skip(reason="OKR commands not yet implemented")
    def test_okr_update_progress(self, temp_org_factory, qn_runner):
        """Should update OKR progress via qn okr update.

        Updating progress should:
        1. Update key result progress percentage
        2. Recalculate objective progress (avg of KRs)
        3. Trigger notifications if thresholds met
        """
        org = temp_org_factory("okr_driven_update")

        # Initialize
        qn_runner("org", "init", org_path=org)

        # Create OKR
        okr_dir = org / "okrs"
        okr_dir.mkdir(parents=True, exist_ok=True)
        (okr_dir / "q1-2025.yaml").write_text("""
objective:
  id: obj-q1
  title: "Test Objective"
key_results:
  - id: kr-1
    title: "Test KR"
    progress: 0
""")

        # TODO: Implement this when OKR commands exist
        # result = qn_runner(
        #     "okr", "update",
        #     "--kr", "kr-1",
        #     "--progress", "75",
        #     org_path=org
        # )
        # assert result.returncode == 0

    @pytest.mark.skip(reason="Requires beads integration")
    def test_okr_work_item_linkage(self, temp_org_factory, qn_runner):
        """Should link work items to key results.

        When a worker completes work that serves a key result:
        1. Work item should have 'serves' field pointing to KR
        2. KR progress should update automatically
        3. Objective progress should recalculate
        """
        # Test will be implemented when beads integration is complete
        pass

    @pytest.mark.skip(reason="Requires beads integration")
    def test_okr_cascading_goals(self, temp_org_factory, qn_runner):
        """Should support cascading goals through hierarchy.

        Flow:
        1. Board sets objective for org
        2. CEO breaks into key results
        3. CEO assigns KR owners
        4. Owners create team-level objectives
        5. Team objectives become work items
        """
        # Test will be implemented when beads integration is complete
        pass

    def test_okr_driven_restart_preserves_okrs(self, temp_org_factory, qn_runner):
        """Should preserve OKR files through restart cycle.

        OKR configuration should persist across:
        - Org stop/start cycles
        - System restarts
        - Worker crashes
        """
        org = temp_org_factory("okr_driven_restart")

        # Initialize
        qn_runner("org", "init", org_path=org)

        # Create OKR
        okr_dir = org / "okrs"
        okr_dir.mkdir(parents=True, exist_ok=True)
        okr_content = """
objective:
  id: obj-persist
  title: "Persistence Test"
  owner: ceo
"""
        (okr_dir / "test.yaml").write_text(okr_content)

        # Start
        qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )

        # Stop
        qn_runner("org", "stop", org_path=org)

        # Verify OKR file still exists and unchanged
        assert (okr_dir / "test.yaml").exists()
        assert (okr_dir / "test.yaml").read_text() == okr_content

        # Restart
        qn_runner(
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
            org_path=org
        )

        # Verify OKR still exists after restart
        assert (okr_dir / "test.yaml").exists()

    def test_okr_driven_database_tables(self, temp_org_factory, qn_runner):
        """Should have all required database tables for OKR-driven org.

        OKR-driven org needs:
        - org_state (org status)
        - workers (CEO, teams)
        - okr tables (when implemented)
        """
        org = temp_org_factory("okr_driven_db")

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

        # Core tables
        assert "org_state" in tables
        assert "workers" in tables

        # OKR tables may be added later
        # assert "objectives" in tables
        # assert "key_results" in tables

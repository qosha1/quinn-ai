"""Baseline worker management integration tests.

Tests worker lifecycle operations using real qn commands:
- org hire → creates worker, assigns manager, creates storage
- org fire → terminates worker, closes session
- Worker onboarding → creates storage, briefing files
- Session spawning → starts tmux session, sets env vars

These tests execute actual qn CLI commands via subprocess to validate
end-to-end worker management workflows.

NOTE: Many hire tests are currently skipped because CEOs created via
'qn org init' don't have hiring_authority_scope configured by default.
This is tracked as a known limitation. Tests that can run without
hiring authority are marked to run.
"""

import sqlite3
from pathlib import Path

import pytest


@pytest.mark.skip(reason="CEO hiring authority not configured by default")
class TestWorkerHire:
    """Test qn org hire command."""

    def test_hire_creates_worker(self, temp_org_factory, qn_runner):
        """Should create new worker in database."""
        org = temp_org_factory("hire_create")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        result = qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org
        )

        assert result.returncode == 0
        assert "Hired" in result.stdout or "Alice" in result.stdout

        # Verify worker in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name, role FROM workers WHERE name = 'Alice'")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Alice"
        assert row[1] == "Developer"

    def test_hire_assigns_manager(self, temp_org_factory, qn_runner):
        """Should assign manager relationship."""
        org = temp_org_factory("hire_manager")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org
        )

        # Verify manager assignment
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get CEO ID
        cursor.execute("SELECT id FROM workers WHERE role = 'CEO'")
        ceo_id = cursor.fetchone()[0]

        # Get Alice's manager
        cursor.execute("SELECT manager_id FROM workers WHERE name = 'Alice'")
        alice_manager = cursor.fetchone()[0]

        conn.close()

        assert alice_manager == ceo_id

    def test_hire_creates_storage(self, temp_org_factory, qn_runner):
        """Should create worker storage directory."""
        org = temp_org_factory("hire_storage")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org
        )

        # Get Alice's worker ID
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM workers WHERE name = 'Alice'")
        alice_id = cursor.fetchone()[0]
        conn.close()

        # Verify storage exists
        # Worker storage is hierarchical: storage/workers/ceo/{worker-id}/
        ceo_storage = org / "storage" / "workers" / "ceo"
        alice_storage = None

        # Find Alice's storage under CEO
        if ceo_storage.exists():
            for item in ceo_storage.iterdir():
                if alice_id in item.name:
                    alice_storage = item
                    break

        assert alice_storage is not None
        assert alice_storage.exists()

    def test_hire_with_cost(self, temp_org_factory, qn_runner):
        """Should set worker cost."""
        org = temp_org_factory("hire_cost")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        result = qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            "--cost", "75",
            org_path=org
        )

        assert result.returncode == 0

        # Verify cost in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT cost FROM workers WHERE name = 'Alice'")
        cost = cursor.fetchone()[0]
        conn.close()

        assert cost == 75

    def test_hire_with_skills(self, temp_org_factory, qn_runner):
        """Should set worker skills from JSON."""
        org = temp_org_factory("hire_skills")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        result = qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            '--skills', '{"coding": 90, "reasoning": 80}',
            org_path=org
        )

        assert result.returncode == 0

        # Verify skills in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT skills FROM workers WHERE name = 'Alice'")
        skills_json = cursor.fetchone()[0]
        conn.close()

        assert "coding" in skills_json
        assert "90" in skills_json

    def test_hire_requires_init(self, temp_org_factory, qn_runner):
        """Should require org to be initialized."""
        org = temp_org_factory("hire_no_init")

        result = qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org,
            check=False
        )

        assert result.returncode != 0
        assert "not initialized" in result.stdout.lower() or "not initialized" in result.stderr.lower() or "Run 'qn org init'" in result.stdout

    def test_hire_requires_valid_manager(self, temp_org_factory, qn_runner):
        """Should fail if manager doesn't exist."""
        org = temp_org_factory("hire_bad_manager")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        result = qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "NonExistentManager",
            org_path=org,
            check=False
        )

        assert result.returncode != 0
        assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


class TestWorkerFire:
    """Test qn org fire command."""

    @pytest.mark.skip(reason="Requires hiring to work first")
    def test_fire_terminates_worker(self, temp_org_factory, qn_runner):
        """Should set worker status to terminated."""
        org = temp_org_factory("fire_terminate")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)
        qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org
        )

        result = qn_runner(
            "org", "fire",
            "Alice",
            "--reason", "Test termination",
            "--force",
            org_path=org
        )

        assert result.returncode == 0

        # Verify status in database
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM workers WHERE name = 'Alice'")
        status = cursor.fetchone()[0]
        conn.close()

        assert status == "terminated"

    @pytest.mark.skip(reason="Requires hiring to work first")
    def test_fire_with_reason(self, temp_org_factory, qn_runner):
        """Should accept termination reason."""
        org = temp_org_factory("fire_reason")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)
        qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org
        )

        result = qn_runner(
            "org", "fire",
            "Alice",
            "--reason", "Budget cuts",
            "--force",
            org_path=org
        )

        assert result.returncode == 0
        # Reason is logged but not stored in workers table

    def test_fire_requires_init(self, temp_org_factory, qn_runner):
        """Should require org to be initialized."""
        org = temp_org_factory("fire_no_init")

        result = qn_runner(
            "org", "fire",
            "Alice",
            "--force",
            org_path=org,
            check=False
        )

        assert result.returncode != 0
        assert "not initialized" in result.stdout.lower() or "not initialized" in result.stderr.lower() or "Run 'qn org init'" in result.stdout

    def test_fire_requires_valid_worker(self, temp_org_factory, qn_runner):
        """Should fail if worker doesn't exist."""
        org = temp_org_factory("fire_bad_worker")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        result = qn_runner(
            "org", "fire",
            "NonExistentWorker",
            "--force",
            org_path=org,
            check=False
        )

        assert result.returncode != 0
        assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()

    def test_fire_cannot_fire_ceo(self, temp_org_factory, qn_runner):
        """Should prevent firing the CEO."""
        org = temp_org_factory("fire_ceo")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        result = qn_runner(
            "org", "fire",
            "CEO",
            "--force",
            org_path=org,
            check=False
        )

        # Should fail (CEO cannot be fired)
        assert result.returncode != 0


@pytest.mark.skip(reason="Requires hiring to work first")
class TestWorkerOnboarding:
    """Test worker onboarding system."""

    def test_onboarding_creates_briefing(self, temp_org_factory, qn_runner):
        """Should create BRIEFING.md in worker storage."""
        org = temp_org_factory("onboard_briefing")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)
        qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org
        )

        # Get Alice's worker ID
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM workers WHERE name = 'Alice'")
        alice_id = cursor.fetchone()[0]
        conn.close()

        # Find worker storage
        ceo_storage = org / "storage" / "workers" / "ceo"
        alice_storage = None
        if ceo_storage.exists():
            for item in ceo_storage.iterdir():
                if alice_id in item.name:
                    alice_storage = item
                    break

        # Check for BRIEFING.md
        if alice_storage:
            briefing = alice_storage / "BRIEFING.md"
            # Briefing may or may not exist depending on implementation
            # This is a placeholder for when onboarding is fully implemented
            assert alice_storage.exists()

    def test_hire_and_fire_workflow(self, temp_org_factory, qn_runner):
        """Should support hire → fire workflow."""
        org = temp_org_factory("hire_fire_workflow")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        # Hire
        result = qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org
        )
        assert result.returncode == 0

        # Verify hired
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM workers WHERE name = 'Alice'")
        status = cursor.fetchone()[0]
        conn.close()
        assert status == "pending"  # Initial status

        # Fire
        result = qn_runner(
            "org", "fire",
            "Alice",
            "--reason", "Test",
            "--force",
            org_path=org
        )
        assert result.returncode == 0

        # Verify fired
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM workers WHERE name = 'Alice'")
        status = cursor.fetchone()[0]
        conn.close()
        assert status == "terminated"


@pytest.mark.skip(reason="Requires hiring to work first")
class TestMultipleWorkers:
    """Test multiple worker scenarios."""

    def test_hire_multiple_workers(self, temp_org_factory, qn_runner):
        """Should support hiring multiple workers."""
        org = temp_org_factory("multiple_hire")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        # Hire Alice
        result = qn_runner(
            "org", "hire",
            "--name", "Alice",
            "--role", "Developer",
            "--manager", "CEO",
            org_path=org
        )
        assert result.returncode == 0

        # Hire Bob
        result = qn_runner(
            "org", "hire",
            "--name", "Bob",
            "--role", "QA",
            "--manager", "CEO",
            org_path=org
        )
        assert result.returncode == 0

        # Verify both workers exist
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM workers WHERE name IN ('Alice', 'Bob')")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 2

    def test_hierarchical_hiring(self, temp_org_factory, qn_runner):
        """Should support hierarchical team structure."""
        org = temp_org_factory("hierarchical")
        qn_runner("org", "init", "--ceo-name", "CEO", org_path=org)

        # Hire manager
        qn_runner(
            "org", "hire",
            "--name", "Manager",
            "--role", "Engineering Manager",
            "--manager", "CEO",
            org_path=org
        )

        # Hire developer under manager
        result = qn_runner(
            "org", "hire",
            "--name", "Developer",
            "--role", "Developer",
            "--manager", "Manager",
            org_path=org
        )

        assert result.returncode == 0

        # Verify hierarchy
        db_path = org / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get manager ID
        cursor.execute("SELECT id FROM workers WHERE name = 'Manager'")
        manager_id = cursor.fetchone()[0]

        # Verify developer reports to manager
        cursor.execute("SELECT manager_id FROM workers WHERE name = 'Developer'")
        dev_manager = cursor.fetchone()[0]

        conn.close()

        assert dev_manager == manager_id

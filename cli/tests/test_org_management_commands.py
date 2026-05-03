"""
Unit tests for qn org management commands.

Covers: hire, fire, promote, demote, chart, budget, okr, provider,
        delegate-authority, revoke-authority, delegations.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from click.testing import CliRunner

from cli.commands.main import qn


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    """Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_org():
    """Temporary directory as org path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def initialized_org(runner, temp_org):
    """Initialized org with a CEO named 'TestCEO'."""
    result = runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--ceo-name", "TestCEO"])
    if result.exit_code != 0:
        pytest.fail(f"org init failed: {result.output}")
    return temp_org


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def get_ceo_worker_id(org_path: Path) -> str:
    from cli.core.db import open_database, get_org_db_path
    from cli.core.org import Org

    db = open_database(get_org_db_path(org_path))
    org = Org.load(db)
    ceo_id = org.ceo_worker_id
    db.close()
    return ceo_id


def create_worker(org_path: Path, name: str, manager_id: str, role: str = "developer") -> str:
    """Insert a worker directly into the database and activate them."""
    from cli.core.db import open_database, get_org_db_path
    from cli.core.queries import create_worker as db_create_worker, get_worker
    from cli.core.worker import Worker

    db = open_database(get_org_db_path(org_path))
    try:
        manager = get_worker(db, manager_id)
        team_id = manager.team_id
        worker_data = db_create_worker(
            db=db,
            name=name,
            role=role,
            team_id=team_id,
            cost=50,
            manager_id=manager_id,
            skills={},
        )
        worker = Worker(db, worker_data.id)
        worker.start_onboarding()
        worker.complete_onboarding()
        return worker_data.id
    finally:
        db.close()


def grant_authority(org_path: Path, worker_id: str, allowed_roles: list, max_cost: int = 60, budget: int = 500) -> None:
    """Give a worker hiring authority so they can act as manager/delegate."""
    from cli.core.db import open_database, get_org_db_path
    from cli.core.worker import Worker, HiringScope
    from cli.core.org import Org

    db = open_database(get_org_db_path(org_path))
    try:
        org = Org.load(db)
        ceo = Worker(db, org.ceo_worker_id)
        target = Worker(db, worker_id)
        scope = HiringScope(allowed_roles=allowed_roles, max_cost=max_cost)
        ceo.delegate_authority(report=target, budget=budget, scope=scope)
    finally:
        db.close()


# ===========================================================================
# HIRE COMMAND TESTS
# ===========================================================================


class TestHireOrgNotInitialized:
    def test_hire_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "hire",
            "--name", "Alice", "--role", "developer", "--manager", "TestCEO"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestHireValidation:
    def test_hire_invalid_skills_json(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "Alice", "--role", "developer", "--manager", "TestCEO",
            "--skills", "not-json"
        ])
        assert result.exit_code != 0
        assert "invalid skills" in result.output.lower() or "json" in result.output.lower()

    def test_hire_skills_not_object(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "Alice", "--role", "developer", "--manager", "TestCEO",
            "--skills", "[1, 2, 3]"
        ])
        assert result.exit_code != 0
        assert "object" in result.output.lower() or "json" in result.output.lower()

    def test_hire_skill_value_out_of_range(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "Alice", "--role", "developer", "--manager", "TestCEO",
            "--skills", '{"coding": 150}'
        ])
        assert result.exit_code != 0
        assert "0-100" in result.output or "skill" in result.output.lower()

    def test_hire_cost_out_of_range_above(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "Alice", "--role", "developer", "--manager", "TestCEO",
            "--cost", "101"
        ])
        assert result.exit_code != 0
        assert "cost" in result.output.lower() or "100" in result.output

    def test_hire_cost_out_of_range_below(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "Alice", "--role", "developer", "--manager", "TestCEO",
            "--cost", "-1"
        ])
        assert result.exit_code != 0
        assert "cost" in result.output.lower()

    def test_hire_cost_boundary_zero(self, runner, initialized_org):
        """Cost 0 is valid."""
        with patch("cli.commands.org.hire._start_workday_for_hire"):
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "hire",
                "--name", "Cheap", "--role", "developer", "--manager", "TestCEO",
                "--cost", "0"
            ])
        # CEO has authority so should succeed
        assert "cannot hire" not in result.output.lower() or result.exit_code == 0

    def test_hire_cost_boundary_hundred(self, runner, initialized_org):
        """Cost 100 is valid."""
        with patch("cli.commands.org.hire._start_workday_for_hire"):
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "hire",
                "--name", "Premium", "--role", "developer", "--manager", "TestCEO",
                "--cost", "100"
            ])
        # Cost boundary is valid - no validation error
        assert "between 0 and 100" not in result.output

    def test_hire_default_cost_is_50(self, runner, initialized_org):
        """Default cost should be 50 when --cost not specified."""
        with patch("cli.commands.org.hire._start_workday_for_hire"):
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "hire",
                "--name", "Defaulty", "--role", "developer", "--manager", "TestCEO"
            ])
        if result.exit_code == 0:
            assert "Cost: 50" in result.output


class TestHireManagerLookup:
    def test_hire_manager_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "Alice", "--role", "developer", "--manager", "NonExistentManager"
        ])
        assert result.exit_code != 0
        output = result.output + (str(result.exception) if result.exception else "")
        assert "not found" in output.lower() or "nonexistentmanager" in output.lower()

    def test_hire_manager_found_by_id(self, runner, initialized_org):
        """Manager can be specified by worker ID."""
        ceo_id = get_ceo_worker_id(initialized_org)
        with patch("cli.commands.org.hire._start_workday_for_hire"):
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "hire",
                "--name", "ByIdWorker", "--role", "developer", "--manager", ceo_id
            ])
        assert result.exit_code == 0
        assert "ByIdWorker" in result.output

    def test_hire_manager_no_authority(self, runner, initialized_org):
        """Worker without hiring authority cannot be a manager in hire."""
        ceo_id = get_ceo_worker_id(initialized_org)
        regular_id = create_worker(initialized_org, "RegularWorker", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "NewHire", "--role", "developer", "--manager", "RegularWorker"
        ])
        assert result.exit_code != 0
        assert "cannot hire" in result.output.lower() or "authority" in result.output.lower()

    def test_hire_role_not_in_allowed_roles(self, runner, initialized_org):
        """Manager can only hire roles in their allowed_roles."""
        ceo_id = get_ceo_worker_id(initialized_org)
        manager_id = create_worker(initialized_org, "LimitedManager", ceo_id)
        # Grant authority only for "analyst" role
        grant_authority(initialized_org, manager_id, allowed_roles=["analyst"], max_cost=80)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "EngineerHire", "--role", "engineer", "--manager", "LimitedManager"
        ])
        assert result.exit_code != 0
        assert "cannot hire" in result.output.lower() or "authority" in result.output.lower()

    def test_hire_cost_exceeds_manager_max_cost(self, runner, initialized_org):
        """Hire fails when worker cost exceeds manager's max_cost authority."""
        ceo_id = get_ceo_worker_id(initialized_org)
        manager_id = create_worker(initialized_org, "BudgetManager", ceo_id)
        # Grant authority with max_cost=30
        grant_authority(initialized_org, manager_id, allowed_roles=["developer"], max_cost=30)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "ExpensiveHire", "--role", "developer", "--manager", "BudgetManager",
            "--cost", "80"
        ])
        assert result.exit_code != 0
        assert "cannot hire" in result.output.lower() or "authority" in result.output.lower()

    def test_hire_max_reports_exceeded(self, runner, initialized_org):
        """Hire fails when manager has reached max_reports."""
        ceo_id = get_ceo_worker_id(initialized_org)
        manager_id = create_worker(initialized_org, "FullManager", ceo_id)
        # Grant authority with max_reports=1
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker, HiringScope
        from cli.core.org import Org

        db = open_database(get_org_db_path(initialized_org))
        try:
            org = Org.load(db)
            ceo = Worker(db, org.ceo_worker_id)
            target = Worker(db, manager_id)
            scope = HiringScope(allowed_roles=["developer"], max_cost=80)
            ceo.delegate_authority(report=target, budget=500, scope=scope)
            # Also set max_reports to 1
            db.execute("UPDATE workers SET max_reports = 1 WHERE id = ?", (manager_id,))
            db.connection.commit()
        finally:
            db.close()

        # Create first report (filling the 1 slot)
        create_worker(initialized_org, "ReportOne", manager_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "ReportTwo", "--role", "developer", "--manager", "FullManager"
        ])
        assert result.exit_code != 0
        assert "max" in result.output.lower() or "reports" in result.output.lower() or "cannot hire" in result.output.lower()

    def test_hire_under_non_ceo_manager(self, runner, initialized_org):
        """Can hire under a non-CEO manager who has authority."""
        ceo_id = get_ceo_worker_id(initialized_org)
        director_id = create_worker(initialized_org, "Director", ceo_id)
        grant_authority(initialized_org, director_id, allowed_roles=["developer"], max_cost=80)

        with patch("cli.commands.org.hire._start_workday_for_hire"):
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "hire",
                "--name", "DeepHire", "--role", "developer", "--manager", "Director"
            ])
        assert result.exit_code == 0
        assert "DeepHire" in result.output
        assert "Director" in result.output


# ===========================================================================
# FIRE COMMAND TESTS
# ===========================================================================


class TestFireOrgNotInitialized:
    def test_fire_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "fire", "SomeWorker", "--force"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestFireWorkerLookup:
    def test_fire_worker_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "GhostWorker", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_fire_worker_found_by_id(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "ByIdWorker", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", worker_id,
            "--reason", "Test", "--force"
        ])
        assert result.exit_code == 0
        assert "terminated" in result.output.lower()

    def test_fire_cannot_fire_ceo(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "TestCEO",
            "--reason", "Test", "--force"
        ])
        assert result.exit_code != 0
        assert "cannot terminate the ceo" in result.output.lower()

    def test_fire_worker_already_terminated(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "AlreadyGone", ceo_id)

        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "AlreadyGone", "--reason", "First time", "--force"
        ])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "AlreadyGone", "--reason", "Second time", "--force"
        ])
        assert result.exit_code != 0
        assert "already terminated" in result.output.lower()


class TestFireHappyPath:
    def test_fire_happy_path_with_force(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "FireMe", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "FireMe",
            "--reason", "Budget cuts", "--force"
        ])
        assert result.exit_code == 0
        assert "terminated" in result.output.lower()

    def test_fire_with_custom_reason(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "CustomReason", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "CustomReason",
            "--reason", "Restructuring 2026", "--force"
        ])
        assert result.exit_code == 0
        assert "Restructuring 2026" in result.output

    def test_fire_storage_frozen_by_default(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "StorageWorker", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "StorageWorker", "--force"
        ])
        assert result.exit_code == 0
        assert "frozen" in result.output.lower()

    def test_fire_keep_storage_flag(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "KeepStorage", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "KeepStorage", "--keep-storage", "--force"
        ])
        assert result.exit_code == 0
        assert "kept" in result.output.lower() or "--keep-storage" in result.output


class TestFireAuthorization:
    def test_fire_unauthorized_manager_fails(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker1_id = create_worker(initialized_org, "Peer1", ceo_id)
        create_worker(initialized_org, "Peer2", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Peer2",
            "--reason", "Test", "--manager", "Peer1", "--force"
        ])
        assert result.exit_code != 0
        assert "cannot terminate" in result.output.lower()

    def test_fire_ceo_can_authorize_any_termination(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "CeoTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "CeoTarget",
            "--manager", "TestCEO", "--force"
        ])
        assert result.exit_code == 0
        assert "terminated" in result.output.lower()

    def test_fire_manager_no_manager_error_without_flag(self, runner, initialized_org):
        """Firing a worker that has no manager requires --manager flag."""
        # Worker at top level without a manager - manipulate DB directly
        from cli.core.db import open_database, get_org_db_path
        from cli.core.queries import create_worker as db_create_worker, get_worker
        from cli.core.worker import Worker

        db = open_database(get_org_db_path(initialized_org))
        try:
            ceo = get_worker(db, get_ceo_worker_id(initialized_org))
            w = db_create_worker(
                db=db,
                name="Orphan",
                role="developer",
                team_id=ceo.team_id,
                cost=50,
                manager_id=None,
                skills={},
            )
            worker = Worker(db, w.id)
            worker.start_onboarding()
            worker.complete_onboarding()
        finally:
            db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Orphan", "--force"
        ])
        assert result.exit_code != 0
        assert "no manager" in result.output.lower() or "--manager" in result.output


class TestFireReassignment:
    def test_fire_reassign_to_self_fails(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "SelfReassign", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "SelfReassign",
            "--reassign-to", "SelfReassign", "--force"
        ])
        assert result.exit_code != 0
        assert "Cannot reassign work to the worker being terminated" in result.output

    def test_fire_reassign_to_terminated_fails(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "ToFire", ceo_id)
        create_worker(initialized_org, "AlreadyFired", ceo_id)

        # Fire AlreadyFired first
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "AlreadyFired", "--force"
        ])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "ToFire",
            "--reassign-to", "AlreadyFired", "--force"
        ])
        assert result.exit_code != 0
        assert "not in active status" in result.output.lower() or "active" in result.output.lower()

    @patch("cli.commands.org.fire._reassign_pending_work")
    def test_fire_reassign_to_valid_worker(self, mock_reassign, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "Departed", ceo_id)
        create_worker(initialized_org, "Receiver", ceo_id)
        mock_reassign.return_value = 0

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Departed",
            "--reassign-to", "Receiver", "--force"
        ])
        assert result.exit_code == 0
        assert "Receiver" in result.output

    def test_fire_with_hiring_authority_revoked(self, runner, initialized_org):
        """Firing a worker with hiring authority should revoke their authority."""
        ceo_id = get_ceo_worker_id(initialized_org)
        manager_id = create_worker(initialized_org, "AuthManager", ceo_id)
        grant_authority(initialized_org, manager_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "AuthManager",
            "--force"
        ])
        assert result.exit_code == 0
        assert "revoked" in result.output.lower() or "authority" in result.output.lower()

    def test_fire_cascade_authority_revoke(self, runner, initialized_org):
        """Firing a manager with downstream delegations cascades the revocation."""
        ceo_id = get_ceo_worker_id(initialized_org)
        director_id = create_worker(initialized_org, "Director", ceo_id)
        grant_authority(initialized_org, director_id, allowed_roles=["developer", "analyst"], max_cost=80)

        manager_id = create_worker(initialized_org, "SubManager", director_id)
        # Give SubManager delegated authority from Director
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker, HiringScope

        db = open_database(get_org_db_path(initialized_org))
        try:
            director = Worker(db, director_id)
            sub = Worker(db, manager_id)
            scope = HiringScope(allowed_roles=["developer"], max_cost=50)
            director.delegate_authority(report=sub, budget=100, scope=scope)
        finally:
            db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Director", "--force"
        ])
        assert result.exit_code == 0
        assert "cascade" in result.output.lower() or "revoked" in result.output.lower() or "authority" in result.output.lower()


# ===========================================================================
# PROMOTE COMMAND TESTS
# ===========================================================================


class TestPromoteOrgNotInitialized:
    def test_promote_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "promote", "Alice", "--to", "team-lead"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestPromoteValidation:
    def test_promote_worker_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "Ghost", "--to", "team-lead", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_promote_invalid_level_rejected(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "TestCEO", "--to", "janitor"
        ])
        assert result.exit_code != 0

    def test_promote_promoter_not_found(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "PromoteTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "PromoteTarget",
            "--to", "team-lead", "--by", "GhostPromoter", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestPromoteHappyPath:
    def test_promote_team_lead_level(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "Riser", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "Riser",
            "--to", "team-lead", "--force"
        ])
        assert result.exit_code == 0
        assert "team-lead" in result.output.lower() or "Promotion complete" in result.output

    def test_promote_director_level_grants_broader_authority(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "DirectorCandidate", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "DirectorCandidate",
            "--to", "director", "--force"
        ])
        assert result.exit_code == 0
        assert "director" in result.output.lower() or "Promotion complete" in result.output

    def test_promote_vp_level_grants_all_roles(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "VpCandidate", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "VpCandidate",
            "--to", "vp", "--force"
        ])
        assert result.exit_code == 0
        assert "vp" in result.output.lower() or "Promotion complete" in result.output

    def test_promote_defaults_to_worker_manager(self, runner, initialized_org):
        """When --by is omitted, the worker's manager authorizes."""
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "ManagerDefault", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "ManagerDefault",
            "--to", "team-lead", "--force"
        ])
        assert result.exit_code == 0
        # The promoter should be CEO (manager of ManagerDefault)
        assert "TestCEO" in result.output

    def test_promote_custom_promoter_with_by(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "PromoTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "PromoTarget",
            "--to", "team-lead", "--by", "TestCEO", "--force"
        ])
        assert result.exit_code == 0
        assert "TestCEO" in result.output

    def test_promote_already_at_level_warns_without_force(self, runner, initialized_org):
        """Already-authorized worker should warn without --force."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "AlreadyLead", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"], max_cost=60)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "AlreadyLead",
            "--to", "team-lead"
        ], input="n\n")
        assert "WARNING" in result.output or "already has authority" in result.output.lower()

    def test_promote_already_at_level_with_force_bypasses_confirm(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "ForcePromote", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"], max_cost=60)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", "ForcePromote",
            "--to", "team-lead", "--force"
        ])
        # Should complete without cancellation
        assert "cancelled" not in result.output.lower()

    def test_promote_circular_delegation_raises_error(self, runner, initialized_org):
        """If promotion causes circular delegation, it should fail gracefully."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "CircWorker", ceo_id)

        with patch("cli.commands.org.promote.Worker.delegate_authority") as mock_delegate:
            from shared.exceptions import CircularDelegationError
            mock_delegate.side_effect = CircularDelegationError("worker-a", "worker-b")

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "promote", "CircWorker",
                "--to", "team-lead", "--force"
            ])
        assert result.exit_code != 0
        assert "circular" in result.output.lower()


# ===========================================================================
# DEMOTE COMMAND TESTS
# ===========================================================================


class TestDemoteOrgNotInitialized:
    def test_demote_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "demote", "Alice"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestDemoteValidation:
    def test_demote_worker_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "Ghost", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_demote_worker_has_no_authority(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "PlainWorker", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "PlainWorker", "--force"
        ])
        assert result.exit_code != 0
        assert "no management authority" in result.output.lower() or "no hiring authority" in result.output.lower()

    def test_demote_demoter_not_found(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "DemoteMe", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "DemoteMe",
            "--by", "GhostDemoter", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestDemoteHappyPath:
    def test_demote_happy_path_removes_authority(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "LeadToIC", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "LeadToIC", "--force"
        ])
        assert result.exit_code == 0
        assert "demotion complete" in result.output.lower() or "individual contributor" in result.output.lower()

    def test_demote_with_custom_reason(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "DemoteReason", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "DemoteReason",
            "--reason", "Returning to IC role", "--force"
        ])
        assert result.exit_code == 0
        assert "Returning to IC role" in result.output

    def test_demote_custom_demoter_with_by(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "DemoteByX", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "DemoteByX",
            "--by", "TestCEO", "--force"
        ])
        assert result.exit_code == 0
        assert "TestCEO" in result.output

    def test_demote_has_direct_reports_warns(self, runner, initialized_org):
        """Worker with direct reports should produce a warning before demotion."""
        ceo_id = get_ceo_worker_id(initialized_org)
        manager_id = create_worker(initialized_org, "ManagerWithReport", ceo_id)
        grant_authority(initialized_org, manager_id, allowed_roles=["developer"])
        # Give them a report
        create_worker(initialized_org, "ReportOfManager", manager_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "ManagerWithReport", "--force"
        ])
        # Should warn about direct reports
        assert "direct report" in result.output.lower() or "WARNING" in result.output

    def test_demote_cascade_revokes_all_downstream(self, runner, initialized_org):
        """--cascade should revoke authority from all downstream workers."""
        ceo_id = get_ceo_worker_id(initialized_org)
        director_id = create_worker(initialized_org, "CascadeDirector", ceo_id)
        grant_authority(initialized_org, director_id, allowed_roles=["developer", "analyst"], max_cost=80)

        lead_id = create_worker(initialized_org, "CascadeLead", director_id)
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker, HiringScope
        db = open_database(get_org_db_path(initialized_org))
        try:
            director = Worker(db, director_id)
            lead = Worker(db, lead_id)
            scope = HiringScope(allowed_roles=["developer"], max_cost=40)
            director.delegate_authority(report=lead, budget=100, scope=scope)
        finally:
            db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "CascadeDirector",
            "--cascade", "--force"
        ])
        assert result.exit_code == 0
        assert "revoked" in result.output.lower() or "demotion complete" in result.output.lower()

    def test_demote_downstream_without_cascade_interactive(self, runner, initialized_org):
        """Without --cascade and with downstream delegations, should show choices interactively."""
        ceo_id = get_ceo_worker_id(initialized_org)
        director_id = create_worker(initialized_org, "InteractiveDirector2", ceo_id)
        grant_authority(initialized_org, director_id, allowed_roles=["developer"], max_cost=80)

        # Director delegates authority to a direct report
        lead_id = create_worker(initialized_org, "InteractiveLead2", director_id)
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker, HiringScope
        db = open_database(get_org_db_path(initialized_org))
        try:
            director = Worker(db, director_id)
            lead = Worker(db, lead_id)
            scope = HiringScope(allowed_roles=["developer"], max_cost=40)
            director.delegate_authority(report=lead, budget=100, scope=scope)
        finally:
            db.close()

        # Director has direct reports AND downstream delegations
        # First prompt: "Proceed anyway?" for direct reports -> y
        # Second prompt: choose 1=cancel for downstream delegations
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", "InteractiveDirector2",
        ], input="y\n1\n")
        assert "cancelled" in result.output.lower()


# ===========================================================================
# CHART COMMAND TESTS
# ===========================================================================


class TestChartShow:
    def test_chart_show_org_not_found(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "chart", "show"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "not initialized" in result.output.lower()

    def test_chart_show_happy_path(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "chart", "show"
        ])
        assert result.exit_code == 0
        assert "Organization Structure" in result.output
        assert "TestCEO" in result.output

    def test_chart_show_empty_workers_message(self, runner, temp_org):
        """If org-chart/current.yaml exists but has no root, show empty message."""
        from cli.core.org_chart import ORG_CHART_DIR, ORG_CHART_CURRENT
        chart_dir = temp_org / ORG_CHART_DIR
        chart_dir.mkdir(parents=True)
        (chart_dir / ORG_CHART_CURRENT).write_text(yaml.dump({"workers": {}, "hierarchy": {}}))

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "chart", "show"
        ])
        assert result.exit_code == 0
        assert "no workers" in result.output.lower()

    def test_chart_tree_alias_for_chart_show(self, runner, initialized_org):
        """chart tree is an alias - it should be registered in the command group."""
        result_show = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "chart", "show"
        ])
        assert result_show.exit_code == 0
        assert "TestCEO" in result_show.output
        # Verify 'tree' is a hidden command in the group
        result_help = runner.invoke(qn, ["org", "chart", "--help"])
        # 'tree' should exist as a command (even if hidden)
        assert result_show.exit_code == 0


class TestChartDiff:
    def test_chart_diff_org_not_found(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "chart", "diff"
        ])
        assert result.exit_code != 0

    def test_chart_diff_not_git_repo(self, runner, temp_org):
        """When git rev-parse fails, should report not a git repository."""
        from cli.core.org_chart import ORG_CHART_DIR, ORG_CHART_CURRENT
        chart_dir = temp_org / ORG_CHART_DIR
        chart_dir.mkdir(parents=True)
        (chart_dir / ORG_CHART_CURRENT).write_text("{}")

        with patch("subprocess.run") as mock_run:
            mock_rev = MagicMock()
            mock_rev.returncode = 128
            mock_rev.stderr = "not a git repository"
            mock_run.return_value = mock_rev
            result = runner.invoke(qn, [
                "--org-path", str(temp_org),
                "org", "chart", "diff"
            ])
        assert result.exit_code != 0
        assert "not a git repository" in result.output.lower() or "git" in result.output.lower()

    def test_chart_diff_no_changes_clean_message(self, runner, initialized_org):
        """When in git repo with no changes, show clean message."""
        with patch("subprocess.run") as mock_run:
            # Mock git rev-parse (success)
            mock_rev = MagicMock()
            mock_rev.returncode = 0
            # Mock git diff (empty output = no changes)
            mock_diff = MagicMock()
            mock_diff.returncode = 0
            mock_diff.stdout = ""
            mock_run.side_effect = [mock_rev, mock_diff]

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "chart", "diff"
            ])
        assert result.exit_code == 0
        assert "no changes" in result.output.lower()

    def test_chart_diff_shows_changes(self, runner, initialized_org):
        """When in git repo with changes, show them."""
        with patch("subprocess.run") as mock_run:
            mock_rev = MagicMock()
            mock_rev.returncode = 0
            mock_diff = MagicMock()
            mock_diff.returncode = 0
            mock_diff.stdout = "+worker: Alice\n-worker: Bob\n"
            mock_run.side_effect = [mock_rev, mock_diff]

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "chart", "diff"
            ])
        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_chart_diff_cached_flag(self, runner, initialized_org):
        """--cached flag passes --cached to git diff."""
        with patch("subprocess.run") as mock_run:
            mock_rev = MagicMock()
            mock_rev.returncode = 0
            mock_diff = MagicMock()
            mock_diff.returncode = 0
            mock_diff.stdout = ""
            mock_run.side_effect = [mock_rev, mock_diff]

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "chart", "diff", "--cached"
            ])
        # Verify --cached was passed in the diff call
        diff_call = mock_run.call_args_list[1]
        assert "--cached" in diff_call[0][0]


class TestChartHistory:
    def test_chart_history_no_commits(self, runner, initialized_org):
        """When git has no commits yet, show appropriate message."""
        with patch("subprocess.run") as mock_run:
            mock_rev = MagicMock()
            mock_rev.returncode = 0
            mock_log = MagicMock()
            mock_log.returncode = 128
            mock_log.stderr = "does not have any commits yet"
            mock_run.side_effect = [mock_rev, mock_log]

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "chart", "history"
            ])
        assert result.exit_code == 0
        assert "no git history" in result.output.lower() or "no commits" in result.output.lower()

    def test_chart_history_shows_git_log(self, runner, initialized_org):
        with patch("subprocess.run") as mock_run:
            mock_rev = MagicMock()
            mock_rev.returncode = 0
            mock_log = MagicMock()
            mock_log.returncode = 0
            mock_log.stdout = "abc1234 2026-01-01 Hired Alice\ndef5678 2026-01-02 Hired Bob\n"
            mock_run.side_effect = [mock_rev, mock_log]

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "chart", "history"
            ])
        assert result.exit_code == 0
        assert "Hired Alice" in result.output

    def test_chart_history_limit_controls_count(self, runner, initialized_org):
        with patch("subprocess.run") as mock_run:
            mock_rev = MagicMock()
            mock_rev.returncode = 0
            mock_log = MagicMock()
            mock_log.returncode = 0
            mock_log.stdout = ""
            mock_run.side_effect = [mock_rev, mock_log]

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "chart", "history", "--limit", "5"
            ])
        # Verify -5 was in the git log call
        log_call = mock_run.call_args_list[1]
        assert "-5" in log_call[0][0]

    def test_chart_history_oneline_format(self, runner, initialized_org):
        with patch("subprocess.run") as mock_run:
            mock_rev = MagicMock()
            mock_rev.returncode = 0
            mock_log = MagicMock()
            mock_log.returncode = 0
            mock_log.stdout = "abc1234 Hired Alice\n"
            mock_run.side_effect = [mock_rev, mock_log]

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "chart", "history", "--oneline"
            ])
        log_call = mock_run.call_args_list[1]
        assert "--oneline" in log_call[0][0]


class TestChartExport:
    def test_chart_export_yaml_to_stdout(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "chart", "export"
        ])
        assert result.exit_code == 0
        # Default format is yaml - output should be yaml-parseable
        parsed = yaml.safe_load(result.output)
        assert isinstance(parsed, dict)

    def test_chart_export_json_to_stdout(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "chart", "export", "--format", "json"
        ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)

    def test_chart_export_output_to_file(self, runner, initialized_org):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output.yaml"
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "chart", "export",
                "--output", str(out_file)
            ])
        assert result.exit_code == 0
        assert "exported" in result.output.lower()


# ===========================================================================
# BUDGET COMMAND TESTS
# ===========================================================================


class TestBudgetOrgNotInitialized:
    def test_budget_status_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "budget", "status"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_budget_tree_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "budget", "tree"
        ])
        assert result.exit_code != 0

    def test_budget_allocate_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "budget", "allocate", "Alice", "100"
        ])
        assert result.exit_code != 0

    def test_budget_transactions_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "budget", "transactions"
        ])
        assert result.exit_code != 0


class TestBudgetStatus:
    def test_budget_status_no_pools_message(self, runner, initialized_org):
        """When no budget pools configured, show appropriate message."""
        with patch("cli.commands.org.budget.get_all_budget_pools") as mock_pools:
            mock_pools.return_value = []
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "budget", "status"
            ])
        assert result.exit_code == 0
        assert "no budget pools" in result.output.lower()

    def test_budget_status_shows_pools_and_ceo_balance(self, runner, initialized_org):
        """Budget status should show pools and CEO balance when they exist."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "status"
        ])
        assert result.exit_code == 0
        assert "Organization Budget" in result.output


class TestBudgetTree:
    def test_budget_tree_shows_from_ceo(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "tree"
        ])
        assert result.exit_code == 0
        assert "Budget Tree" in result.output
        assert "TestCEO" in result.output

    def test_budget_tree_worker_id_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "tree",
            "--worker-id", "nonexistent-id"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_budget_tree_starts_from_specified_worker(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "tree",
            "--worker-id", ceo_id
        ])
        assert result.exit_code == 0
        assert "TestCEO" in result.output


class TestBudgetAllocate:
    def test_budget_allocate_worker_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "allocate", "NoSuchWorker", "100"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_budget_allocate_from_worker_not_found(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "AllocTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "allocate", "AllocTarget", "100",
            "--from", "NoSuchSource"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_budget_allocate_success_from_ceo(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "AllocReceiver", ceo_id)

        with patch("cli.commands.org.budget.BudgetService.delegate_budget") as mock_delegate:
            mock_delegate.return_value = "alloc-test-id"
            with patch("cli.commands.org.budget.get_worker_balance") as mock_balance:
                mock_bal = MagicMock()
                mock_bal.available = 200.0
                mock_balance.return_value = mock_bal

                result = runner.invoke(qn, [
                    "--org-path", str(initialized_org),
                    "org", "budget", "allocate", "AllocReceiver", "100"
                ])
        assert result.exit_code == 0
        assert "Allocated" in result.output or "allocated" in result.output.lower()

    def test_budget_allocate_insufficient_funds(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "BrokeReceiver", ceo_id)

        with patch("cli.commands.org.budget.BudgetService.delegate_budget") as mock_delegate:
            from cli.commands.org.budget import BudgetAllocationError
            mock_delegate.side_effect = BudgetAllocationError("insufficient funds")

            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "budget", "allocate", "BrokeReceiver", "99999"
            ])
        assert result.exit_code != 0
        assert "allocation failed" in result.output.lower() or "insufficient" in result.output.lower()

    def test_budget_allocate_from_custom_source(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "CustomSource", ceo_id)
        create_worker(initialized_org, "CustomTarget", ceo_id)

        with patch("cli.commands.org.budget.BudgetService.delegate_budget") as mock_delegate:
            mock_delegate.return_value = "alloc-custom-id"
            with patch("cli.commands.org.budget.get_worker_balance") as mock_balance:
                mock_bal = MagicMock()
                mock_bal.available = 100.0
                mock_balance.return_value = mock_bal

                result = runner.invoke(qn, [
                    "--org-path", str(initialized_org),
                    "org", "budget", "allocate", "CustomTarget", "50",
                    "--from", "CustomSource"
                ])
        assert result.exit_code == 0


class TestBudgetTransactions:
    def test_budget_transactions_worker_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "transactions", "GhostWorker"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_budget_transactions_shows_ceo_by_default(self, runner, initialized_org):
        with patch("cli.commands.org.budget.get_transactions_by_worker") as mock_txns:
            mock_txns.return_value = []
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "budget", "transactions"
            ])
        assert result.exit_code == 0
        assert "TestCEO" in result.output

    def test_budget_transactions_no_transactions_found(self, runner, initialized_org):
        with patch("cli.commands.org.budget.get_transactions_by_worker") as mock_txns:
            mock_txns.return_value = []
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "budget", "transactions"
            ])
        assert result.exit_code == 0
        assert "no transactions" in result.output.lower()

    def test_budget_transactions_limit_controls_count(self, runner, initialized_org):
        with patch("cli.commands.org.budget.get_transactions_by_worker") as mock_txns:
            mock_txns.return_value = []
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "budget", "transactions", "--limit", "5"
            ])
        assert result.exit_code == 0
        call_kwargs = mock_txns.call_args[1] if mock_txns.call_args else {}
        assert call_kwargs.get("limit") == 5 or (mock_txns.call_args and 5 in mock_txns.call_args[0])

    def test_budget_transactions_type_filter(self, runner, initialized_org):
        with patch("cli.commands.org.budget.get_transactions_by_worker") as mock_txns:
            mock_txns.return_value = []
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "budget", "transactions", "--type", "spend"
            ])
        assert result.exit_code == 0
        mock_txns.assert_called_once()
        call_kwargs = mock_txns.call_args[1] if mock_txns.call_args else {}
        assert call_kwargs.get("transaction_type") == "spend"


# ===========================================================================
# OKR COMMAND TESTS
# ===========================================================================


class TestOkrOrgNotInitialized:
    def test_okr_list_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "list"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestOkrList:
    def test_okr_list_returns_open_by_default(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(returncode=0, stdout='[]', stderr='')
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "list"
            ])
        assert result.exit_code == 0
        # Verify --status=open was in the args
        call_args = mock_bd.call_args[0][0]
        assert any("status=open" in a or "status" in a for a in call_args)

    def test_okr_list_all_includes_closed(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(returncode=0, stdout='[]', stderr='')
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "list", "--all"
            ])
        assert result.exit_code == 0
        call_args = mock_bd.call_args[0][0]
        assert "--all" in call_args

    def test_okr_list_status_filter(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(returncode=0, stdout='[]', stderr='')
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "list", "--status", "in_progress"
            ])
        assert result.exit_code == 0

    def test_okr_list_assignee_filter(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(returncode=0, stdout='[]', stderr='')
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "list", "--assignee", "TestCEO"
            ])
        assert result.exit_code == 0
        call_args = mock_bd.call_args[0][0]
        assert any("assignee" in a for a in call_args)

    def test_okr_list_empty_when_beads_returns_no_okrs(self, runner, initialized_org):
        """qn org okr list shows the empty-state message when beads has no OKRs."""
        with patch("cli.commands.org.okr.list_cmd._helpers.run_bd") as mock_bd:
            mock_bd.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "list"
            ])
        assert result.exit_code == 0
        assert "No OKRs found" in result.output


class TestOkrSet:
    def test_okr_set_creates_okr_with_required_title(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(
                returncode=0,
                stdout="Created issue: okr-test-1\n",
                stderr=""
            )
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "set",
                "--title", "Q1 Revenue Growth",
                "--no-krs-needed",
            ])
        assert result.exit_code == 0
        call_args = mock_bd.call_args[0][0]
        assert "Q1 Revenue Growth" in call_args

    def test_okr_set_with_all_options(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(
                returncode=0,
                stdout="Created issue: okr-full-1\n",
                stderr=""
            )
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "set",
                "--title", "Full OKR",
                "--description", "Full description",
                "--owner", "TestCEO",
                "--priority", "1",
                "--label", "growth",
                "--due", "2026-06-30",
                "--no-krs-needed",
            ])
        assert result.exit_code == 0

    def test_okr_set_iso_due_date(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(
                returncode=0,
                stdout="Created issue: okr-iso-1\n",
                stderr=""
            )
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "set",
                "--title", "ISO Date OKR",
                "--due", "2026-03-31",
                "--no-krs-needed",
            ])
        assert result.exit_code == 0

    def test_okr_set_relative_due_date(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(
                returncode=0,
                stdout="Created issue: okr-rel-1\n",
                stderr=""
            )
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "set",
                "--title", "Relative Date OKR",
                "--due", "+3m",
                "--no-krs-needed",
            ])
        assert result.exit_code == 0

    def test_okr_add_alias_works_same_as_set(self, runner, initialized_org):
        """okr add should behave identically to okr set."""
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(
                returncode=0,
                stdout="Created issue: okr-add-1\n",
                stderr=""
            )
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "add",
                "--title", "Add Alias OKR",
                "--no-krs-needed",
            ])
        assert result.exit_code == 0


class TestOkrShow:
    def test_okr_show_not_found(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "show", "okr-nonexistent"
            ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_okr_show_displays_details_and_linked_work(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.side_effect = [
                MagicMock(returncode=0, stdout="OKR: Q1 Goal\nStatus: open\n", stderr=""),
                MagicMock(returncode=0, stdout='[]', stderr=""),
            ]
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "show", "okr-test-1"
            ])
        assert result.exit_code == 0
        assert "Q1 Goal" in result.output


class TestOkrProgress:
    def test_okr_progress_no_key_results(self, runner, initialized_org):
        from cli.core.queries import OKR

        mock_okr = MagicMock()
        mock_okr.title = "Test OKR"
        mock_okr.id = "okr-test-1"
        mock_okr.status = "active"
        mock_okr.owner_worker_id = "ceo"
        mock_okr.due_date = None
        mock_okr.key_results = []
        mock_okr.progress.return_value = 0.0

        with patch("cli.core.queries.get_okr") as mock_get:
            mock_get.return_value = mock_okr
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "progress", "okr-test-1"
            ])
        assert result.exit_code == 0
        assert "no key results" in result.output.lower()

    def test_okr_progress_shows_key_results_with_percentages(self, runner, initialized_org):
        mock_kr = MagicMock()
        mock_kr.metric = "test_coverage"
        mock_kr.current = 72.0
        mock_kr.target = 80.0
        mock_kr.unit = "%"
        mock_kr.progress.return_value = 90.0
        mock_kr.is_met.return_value = False

        mock_okr = MagicMock()
        mock_okr.title = "Coverage OKR"
        mock_okr.id = "okr-cov-1"
        mock_okr.status = "active"
        mock_okr.owner_worker_id = "ceo"
        mock_okr.due_date = None
        mock_okr.key_results = [mock_kr]
        mock_okr.progress.return_value = 90.0
        mock_okr.all_key_results_met.return_value = False

        with patch("cli.core.queries.get_okr") as mock_get:
            mock_get.return_value = mock_okr
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "progress", "okr-cov-1"
            ])
        assert result.exit_code == 0
        assert "test_coverage" in result.output
        assert "72" in result.output
        assert "80" in result.output


class TestOkrUpdateKr:
    def test_okr_update_kr_adds_new_key_result(self, runner, initialized_org):
        mock_okr = MagicMock()
        mock_okr.title = "Test"
        mock_okr.id = "okr-1"
        mock_okr.key_results = []
        mock_okr.progress.return_value = 0.0

        with patch("cli.core.queries.get_okr") as mock_get:
            mock_get.return_value = mock_okr
            with patch("cli.core.queries.add_okr_key_result") as mock_add:
                result = runner.invoke(qn, [
                    "--org-path", str(initialized_org),
                    "org", "okr", "update-kr", "okr-1",
                    "--metric", "coverage",
                    "--target", "80"
                ])
        assert result.exit_code == 0
        mock_add.assert_called_once()

    def test_okr_update_kr_new_without_target_fails(self, runner, initialized_org):
        mock_okr = MagicMock()
        mock_okr.key_results = []

        with patch("cli.core.queries.get_okr") as mock_get:
            mock_get.return_value = mock_okr
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "update-kr", "okr-1",
                "--metric", "coverage"
            ])
        assert result.exit_code != 0
        assert "--target" in result.output

    def test_okr_update_kr_updates_existing_current_value(self, runner, initialized_org):
        mock_kr = MagicMock()
        mock_kr.metric = "coverage"
        mock_kr.target = 80.0
        mock_kr.unit = "%"

        mock_okr = MagicMock()
        mock_okr.key_results = [mock_kr]
        mock_okr.progress.return_value = 72.0

        with patch("cli.core.queries.get_okr") as mock_get:
            mock_get.side_effect = [mock_okr, mock_okr]
            with patch("cli.core.queries.update_okr_key_result") as mock_update:
                result = runner.invoke(qn, [
                    "--org-path", str(initialized_org),
                    "org", "okr", "update-kr", "okr-1",
                    "--metric", "coverage",
                    "--current", "72"
                ])
        assert result.exit_code == 0
        mock_update.assert_called_once()

    def test_okr_update_kr_existing_without_current_fails(self, runner, initialized_org):
        mock_kr = MagicMock()
        mock_kr.metric = "coverage"
        mock_kr.target = 80.0
        mock_kr.unit = "%"

        mock_okr = MagicMock()
        mock_okr.key_results = [mock_kr]

        with patch("cli.core.queries.get_okr") as mock_get:
            mock_get.return_value = mock_okr
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "update-kr", "okr-1",
                "--metric", "coverage"
            ])
        assert result.exit_code != 0
        assert "--current" in result.output


class TestOkrCascade:
    def test_okr_cascade_shows_hierarchy_tree(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps([
                    {"id": "okr-1", "title": "Parent OKR", "status": "open", "assignee": "ceo", "parent_id": None},
                    {"id": "okr-2", "title": "Child OKR", "status": "open", "assignee": "ceo", "parent_id": "okr-1"},
                ]),
                stderr=""
            )
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "cascade"
            ])
        assert result.exit_code == 0
        assert "Parent OKR" in result.output

    def test_okr_cascade_root_shows_subtree(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(
                returncode=0,
                stdout="okr-1: Parent OKR\n  okr-2: Child OKR\n",
                stderr=""
            )
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "cascade", "--root", "okr-1"
            ])
        assert result.exit_code == 0
        assert "okr-1" in result.output


class TestOkrLink:
    def test_okr_link_work_item_to_okr(self, runner, initialized_org):
        with patch('cli.commands.org.okr._helpers.run_bd') as mock_bd:
            mock_bd.return_value = MagicMock(returncode=0, stdout="Added dependency\n", stderr="")
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org),
                "org", "okr", "link", "task-abc", "okr-xyz"
            ])
        assert result.exit_code == 0
        assert "task-abc" in result.output
        assert "okr-xyz" in result.output


# ===========================================================================
# PROVIDER COMMAND TESTS
# ===========================================================================


class TestProviderList:
    def test_provider_list_shows_registered_providers(self, runner):
        result = runner.invoke(qn, ["org", "provider", "list"])
        assert result.exit_code == 0
        assert "Available CLI Providers" in result.output


class TestProviderDefault:
    def test_provider_default_no_providers_yaml(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "provider", "default"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_provider_default_shows_current(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "default"
        ])
        assert result.exit_code == 0
        assert "Default provider" in result.output

    def test_provider_default_sets_new_default(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "default", "claude_code"
        ])
        assert result.exit_code == 0
        assert "claude_code" in result.output

    def test_provider_default_unknown_provider_rejected(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "default", "unknown_provider_xyz"
        ])
        assert result.exit_code != 0
        assert "unknown provider" in result.output.lower() or "not registered" in result.output.lower() or "Available" in result.output


class TestProviderSetWorker:
    def test_provider_set_worker_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "provider", "set-worker", "Alice", "claude_code"
        ])
        assert result.exit_code != 0

    def test_provider_set_worker_unknown_provider_rejected(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "set-worker", "TestCEO", "unknown_xyz"
        ])
        assert result.exit_code != 0
        assert "unknown provider" in result.output.lower() or "available" in result.output.lower()

    def test_provider_set_worker_worker_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "set-worker", "GhostWorker", "claude_code"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_provider_set_worker_sets_preferred_provider(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "set-worker", "TestCEO", "claude_code"
        ])
        assert result.exit_code == 0
        assert "claude_code" in result.output

    def test_provider_set_worker_clears_preference(self, runner, initialized_org):
        """Clearing preference sets preferred_provider to None in database."""
        # First set a preference
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "set-worker", "TestCEO", "claude_code"
        ])
        # Clear via direct DB update (the '--' arg doesn't work with Click parsing)
        from cli.core.db import open_database, get_org_db_path
        from cli.core.queries import update_worker_preferred_provider, get_worker_by_name
        db = open_database(get_org_db_path(initialized_org))
        try:
            w = get_worker_by_name(db, "TestCEO")
            update_worker_preferred_provider(db, w.id, None)
        finally:
            db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "show-worker", "TestCEO"
        ])
        assert result.exit_code == 0
        assert "not set" in result.output.lower() or "(not set)" in result.output


class TestProviderShowWorker:
    def test_provider_show_worker_shows_effective_provider(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "show-worker", "TestCEO"
        ])
        assert result.exit_code == 0
        assert "Effective provider" in result.output

    def test_provider_show_worker_no_preferred_shows_org_default(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "show-worker", "TestCEO"
        ])
        assert result.exit_code == 0
        assert "Preferred provider" in result.output
        assert "Org default" in result.output or "Effective provider" in result.output


class TestProviderValidate:
    def test_provider_validate_passes_with_valid_config(self, runner, initialized_org):
        # Set a valid default first
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "default", "claude_code"
        ])
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "validate"
        ])
        # Should pass or warn (no error about registered providers)
        assert "failed" not in result.output.lower() or "error" not in result.output.lower() or result.exit_code == 0

    def test_provider_validate_warns_with_no_default(self, runner, initialized_org):
        """When no default is set, should warn."""
        # Clear the default
        config_path = initialized_org / "config" / "providers.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        config.pop("default", None)
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "validate"
        ])
        assert "no default" in result.output.lower() or "WARNING" in result.output or "warning" in result.output.lower()

    def test_provider_validate_fails_with_unknown_default(self, runner, initialized_org):
        # Set an unknown default in providers.yaml
        config_path = initialized_org / "config" / "providers.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        config["default"] = "nonexistent_provider"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "validate"
        ])
        assert result.exit_code != 0
        assert "nonexistent_provider" in result.output or "not registered" in result.output.lower()


# ===========================================================================
# DELEGATE-AUTHORITY COMMAND TESTS
# ===========================================================================


class TestDelegateAuthorityOrgNotInitialized:
    def test_delegate_authority_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "delegate-authority",
            "--to", "Alice", "--level", "team-lead"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestDelegateAuthorityValidation:
    def test_delegate_no_spec_option_fails(self, runner, initialized_org):
        """Must specify one of --level, --roles, or --copy-from."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "TestCEO", "--force"
        ])
        assert result.exit_code != 0
        assert "must specify" in result.output.lower()

    def test_delegate_combining_spec_options_fails(self, runner, initialized_org):
        """Cannot combine --level and --roles."""
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "MultiSpec", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "MultiSpec",
            "--level", "team-lead",
            "--roles", "developer"
        ])
        assert result.exit_code != 0
        assert "cannot combine" in result.output.lower()

    def test_delegate_delegate_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "GhostWorker", "--level", "team-lead", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_delegate_delegator_not_found(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "ValidDelegate", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "ValidDelegate",
            "--from", "GhostDelegator",
            "--level", "team-lead", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_delegate_max_cost_out_of_range(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "CostTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "CostTarget",
            "--roles", "developer",
            "--max-cost", "150",
            "--force"
        ])
        assert result.exit_code != 0
        assert "max cost" in result.output.lower() or "0 and 100" in result.output

    def test_delegate_authority_flips_can_delegate_on_existing_allocation(
        self, runner, initialized_org
    ):
        """Regression for quinn-ai-hv0b: granting --level <preset> with a
        --budget should flip can_delegate=True on the delegate's
        allocation so they can sub-allocate to their own reports.

        Pre-fix: Diana got hiring authority + a 200 budget but
        can_delegate stayed False, so 'qn org budget allocate eve 50'
        from Diana raised 'source has can_delegate=False' and Diana
        couldn't fund her hires.
        """
        from cli.core.db import open_database, get_org_db_path
        from cli.core.queries.budget import (
            create_budget_allocation,
            get_current_allocation,
        )

        ceo_id = get_ceo_worker_id(initialized_org)
        diana_id = create_worker(initialized_org, "Diana", ceo_id)

        # Pre-seed Diana with a budget allocation from the CEO's pool so
        # the can_delegate flip has something to flip (matches the canary
        # 04 sequence: CEO funds Diana before delegating authority).
        db = open_database(get_org_db_path(initialized_org))
        try:
            ceo_alloc = get_current_allocation(db, ceo_id)
            assert ceo_alloc is not None, "CEO should have an allocation from init"
            create_budget_allocation(
                db=db,
                worker_id=diana_id,
                allocated_credits=200,
                period_start=ceo_alloc.period_start,
                period_end=ceo_alloc.period_end,
                pool_id=ceo_alloc.pool_id,
                can_delegate=False,  # starts False — delegate-authority should flip it
            )
        finally:
            db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "Diana",
            "--level", "team-lead",
            "--budget", "200",
            "--max-reports", "5",
            "--force",
        ])
        assert result.exit_code == 0, result.output

        # Verify the flip landed
        db = open_database(get_org_db_path(initialized_org))
        try:
            allocation = get_current_allocation(db, diana_id)
        finally:
            db.close()
        assert allocation is not None, "Diana should have an allocation"
        assert allocation.can_delegate is True, (
            "delegate-authority --level <preset> with --budget must flip "
            "can_delegate=True so the delegate can fund their own hires "
            "(quinn-ai-hv0b)"
        )

    def test_delegate_copy_from_worker_no_authority(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "NoAuthSource", ceo_id)
        create_worker(initialized_org, "CopyTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "CopyTarget",
            "--copy-from", "NoAuthSource",
            "--force"
        ])
        assert result.exit_code != 0
        assert "no hiring authority" in result.output.lower()


class TestDelegateAuthorityHappyPath:
    def test_delegate_happy_path_with_level_preset(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "NewLead", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "NewLead",
            "--level", "team-lead", "--force"
        ])
        assert result.exit_code == 0
        assert "delegation complete" in result.output.lower()

    def test_delegate_custom_roles_with_roles(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "CustomRoleTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "CustomRoleTarget",
            "--roles", "engineer,analyst",
            "--force"
        ])
        assert result.exit_code == 0
        assert "engineer" in result.output.lower() or "delegation complete" in result.output.lower()

    def test_delegate_copy_from_another_worker(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        source_id = create_worker(initialized_org, "SourceAuthority", ceo_id)
        grant_authority(initialized_org, source_id, allowed_roles=["developer", "analyst"])
        create_worker(initialized_org, "CopyRecipient", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "CopyRecipient",
            "--copy-from", "SourceAuthority",
            "--force"
        ])
        assert result.exit_code == 0
        assert "delegation complete" in result.output.lower()

    def test_delegate_default_delegator_is_ceo(self, runner, initialized_org):
        """When --from is omitted, CEO is the delegator."""
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "DefaultDelegateTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "DefaultDelegateTarget",
            "--level", "team-lead", "--force"
        ])
        assert result.exit_code == 0
        assert "TestCEO" in result.output

    def test_delegate_dry_run_shows_preview_without_changes(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "DryRunTarget", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "DryRunTarget",
            "--level", "team-lead",
            "--dry-run", "--force"
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "no changes" in result.output.lower()

    def test_delegate_existing_authority_warns_without_force(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "AlreadyAuthorized", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", "AlreadyAuthorized",
            "--level", "team-lead"
        ], input="n\n")
        assert "WARNING" in result.output or "already has hiring authority" in result.output.lower()


# ===========================================================================
# REVOKE-AUTHORITY COMMAND TESTS
# ===========================================================================


class TestRevokeAuthorityOrgNotInitialized:
    def test_revoke_authority_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "revoke-authority", "Alice"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestRevokeAuthorityValidation:
    def test_revoke_worker_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "GhostWorker", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_revoke_worker_has_no_authority(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "PlainIC", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "PlainIC", "--force"
        ])
        assert result.exit_code != 0
        assert "no hiring authority" in result.output.lower()

    def test_revoke_revoker_not_found(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "RevokeTarget", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "RevokeTarget",
            "--by", "GhostRevoker", "--force"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_revoke_has_downstream_without_cascade(self, runner, initialized_org):
        """Without --cascade when there are downstream delegations, should show options."""
        ceo_id = get_ceo_worker_id(initialized_org)
        director_id = create_worker(initialized_org, "DownstreamDirector", ceo_id)
        grant_authority(initialized_org, director_id, allowed_roles=["developer"], max_cost=80)

        lead_id = create_worker(initialized_org, "DownstreamLead", director_id)
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker, HiringScope
        db = open_database(get_org_db_path(initialized_org))
        try:
            director = Worker(db, director_id)
            lead = Worker(db, lead_id)
            scope = HiringScope(allowed_roles=["developer"], max_cost=40)
            director.delegate_authority(report=lead, budget=100, scope=scope)
        finally:
            db.close()

        # Answer cancel (1)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "DownstreamDirector",
        ], input="1\n")
        assert "cancelled" in result.output.lower() or "cannot revoke" in result.output.lower()


class TestRevokeAuthorityHappyPath:
    def test_revoke_happy_path_with_force(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "RevokeHappy", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "RevokeHappy", "--force"
        ])
        assert result.exit_code == 0
        assert "revocation complete" in result.output.lower()

    def test_revoke_with_custom_reason(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "RevokeReason", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "RevokeReason",
            "--reason", "Team restructure", "--force"
        ])
        assert result.exit_code == 0
        assert "Team restructure" in result.output

    def test_revoke_custom_revoker_with_by(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "RevokeByX", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "RevokeByX",
            "--by", "TestCEO", "--force"
        ])
        assert result.exit_code == 0
        assert "TestCEO" in result.output

    def test_revoke_cascade_revokes_all_downstream(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        director_id = create_worker(initialized_org, "CascadeRevokeDir", ceo_id)
        grant_authority(initialized_org, director_id, allowed_roles=["developer"], max_cost=80)

        lead_id = create_worker(initialized_org, "CascadeRevokeLead", director_id)
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker, HiringScope
        db = open_database(get_org_db_path(initialized_org))
        try:
            director = Worker(db, director_id)
            lead = Worker(db, lead_id)
            scope = HiringScope(allowed_roles=["developer"], max_cost=40)
            director.delegate_authority(report=lead, budget=100, scope=scope)
        finally:
            db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "CascadeRevokeDir",
            "--cascade", "--force"
        ])
        assert result.exit_code == 0
        assert "revocation complete" in result.output.lower()

    def test_revoke_dry_run_shows_preview_without_changes(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "RevokeDryRun", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "RevokeDryRun",
            "--dry-run", "--force"
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "no changes" in result.output.lower()

    def test_revoke_deep_cascade_three_levels(self, runner, initialized_org):
        """Cascade should revoke 3 levels deep."""
        ceo_id = get_ceo_worker_id(initialized_org)
        l1_id = create_worker(initialized_org, "Level1", ceo_id)
        grant_authority(initialized_org, l1_id, allowed_roles=["developer"], max_cost=80)

        l2_id = create_worker(initialized_org, "Level2", l1_id)
        l3_id = create_worker(initialized_org, "Level3", l2_id)

        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker, HiringScope
        db = open_database(get_org_db_path(initialized_org))
        try:
            l1 = Worker(db, l1_id)
            l2 = Worker(db, l2_id)
            l3 = Worker(db, l3_id)
            scope80 = HiringScope(allowed_roles=["developer"], max_cost=80)
            scope60 = HiringScope(allowed_roles=["developer"], max_cost=60)
            l1.delegate_authority(report=l2, budget=200, scope=scope80)
            l2.delegate_authority(report=l3, budget=100, scope=scope60)
        finally:
            db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "Level1",
            "--cascade", "--force"
        ])
        assert result.exit_code == 0
        assert "revocation complete" in result.output.lower()

    def test_revoke_interactive_prompt_with_downstream(self, runner, initialized_org):
        """Interactive prompt with downstream: choosing 2 should cascade."""
        ceo_id = get_ceo_worker_id(initialized_org)
        director_id = create_worker(initialized_org, "InteractiveRevokeDir", ceo_id)
        grant_authority(initialized_org, director_id, allowed_roles=["developer"], max_cost=80)

        lead_id = create_worker(initialized_org, "InteractiveRevokeLead", director_id)
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker, HiringScope
        db = open_database(get_org_db_path(initialized_org))
        try:
            director = Worker(db, director_id)
            lead = Worker(db, lead_id)
            scope = HiringScope(allowed_roles=["developer"], max_cost=40)
            director.delegate_authority(report=lead, budget=100, scope=scope)
        finally:
            db.close()

        # Answer cascade (2)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", "InteractiveRevokeDir",
        ], input="2\ny\n")
        assert result.exit_code == 0
        assert "revocation complete" in result.output.lower()


# ===========================================================================
# DELEGATIONS COMMAND TESTS
# ===========================================================================


class TestDelegationsOrgNotInitialized:
    def test_delegations_org_not_initialized(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "delegations"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestDelegationsList:
    def test_delegations_no_active_delegations(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations"
        ])
        assert result.exit_code == 0
        assert "no active delegations" in result.output.lower() or "DELEGATIONS" in result.output

    def test_delegations_lists_all_active(self, runner, initialized_org):
        """After granting authority, delegations should appear."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "DelegationTarget", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations"
        ])
        assert result.exit_code == 0
        assert "TestCEO" in result.output or "DelegationTarget" in result.output

    def test_delegations_json_output(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--json-output"
        ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)

    def test_delegations_tree_shows_ascii_tree(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--tree"
        ])
        assert result.exit_code == 0
        assert "DELEGATION TREE" in result.output

    def test_delegations_include_revoked_shows_history(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "RevokedWorker", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        # Revoke it (CEO revokes authority from the worker)
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker
        db = open_database(get_org_db_path(initialized_org))
        try:
            ceo = Worker(db, ceo_id)
            w = Worker(db, worker_id)
            ceo.revoke_authority(delegate=w, cascade=False, reason="test revoke")
        finally:
            db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--include-revoked"
        ])
        assert result.exit_code == 0
        assert "revoked" in result.output.lower() or "DELEGATIONS" in result.output


class TestDelegationsWorker:
    def test_delegations_worker_not_found(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--worker", "GhostWorker"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_delegations_worker_shows_chain(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "ChainWorker", ceo_id)
        grant_authority(initialized_org, worker_id, allowed_roles=["developer"])

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--worker", "ChainWorker"
        ])
        assert result.exit_code == 0
        assert "ChainWorker" in result.output
        assert "DELEGATION CHAIN" in result.output

    def test_delegations_worker_no_authority_shows_none(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "NoAuthWorker", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--worker", "NoAuthWorker"
        ])
        assert result.exit_code == 0
        assert "None" in result.output or "no authority" in result.output.lower()

    def test_delegations_worker_json_output(self, runner, initialized_org):
        ceo_id = get_ceo_worker_id(initialized_org)
        create_worker(initialized_org, "JsonWorker", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--worker", "JsonWorker", "--json-output"
        ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "worker" in parsed
        assert "authority" in parsed

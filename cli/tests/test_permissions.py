"""
Unit tests for team membership and permission operations.
"""

import tempfile
from pathlib import Path

import pytest

from cli.core.db import init_database
from cli.core.queries import (
    # Teams and workers (for setup)
    create_team,
    create_worker,
    # Team members
    add_team_member,
    get_team_member,
    update_team_member_role,
    remove_team_member,
    get_team_members_list,
    get_worker_team_memberships,
    get_team_members_by_role,
    # Permissions
    grant_permission,
    get_permission,
    get_permission_for_grantee,
    revoke_permission,
    revoke_permission_for_grantee,
    get_permissions_for_bead,
    get_permissions_for_worker,
    get_permissions_for_team,
    # Effective permissions
    set_effective_permission,
    get_effective_permission,
    delete_effective_permission,
    delete_effective_permissions_for_bead,
    # Permission audit
    log_permission_audit,
    get_permission_audit_for_bead,
    get_permission_audit_for_worker,
    get_permission_denials,
)


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def team(db):
    """Create a test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def worker(db, team):
    """Create a test worker."""
    return create_worker(db, "Alice", "Developer", team.id, 50)


class TestTeamMemberQueries:
    """Test team member CRUD operations."""

    def test_add_team_member(self, db, team, worker):
        """Should add a worker to a team."""
        member = add_team_member(db, team.id, worker.id)
        assert member.team_id == team.id
        assert member.worker_id == worker.id
        assert member.role == "member"
        assert member.joined_at is not None

    def test_add_team_member_with_role(self, db, team, worker):
        """Should add a worker with a specific role."""
        member = add_team_member(db, team.id, worker.id, role="lead")
        assert member.role == "lead"

    def test_get_team_member(self, db, team, worker):
        """Should get a team membership record."""
        add_team_member(db, team.id, worker.id, role="admin")
        member = get_team_member(db, team.id, worker.id)
        assert member is not None
        assert member.role == "admin"

    def test_get_team_member_not_found(self, db, team, worker):
        """Should return None for missing membership."""
        result = get_team_member(db, team.id, worker.id)
        assert result is None

    def test_update_team_member_role(self, db, team, worker):
        """Should update a worker's role in a team."""
        add_team_member(db, team.id, worker.id, role="member")
        update_team_member_role(db, team.id, worker.id, "lead")
        member = get_team_member(db, team.id, worker.id)
        assert member.role == "lead"

    def test_remove_team_member(self, db, team, worker):
        """Should remove a worker from a team."""
        add_team_member(db, team.id, worker.id)
        result = remove_team_member(db, team.id, worker.id)
        assert result is True
        assert get_team_member(db, team.id, worker.id) is None

    def test_remove_team_member_not_found(self, db, team, worker):
        """Should return False when removing non-existent membership."""
        result = remove_team_member(db, team.id, worker.id)
        assert result is False

    def test_get_team_members_list(self, db, team):
        """Should get all members of a team."""
        w1 = create_worker(db, "Alice", "Developer", team.id, 50)
        w2 = create_worker(db, "Bob", "Developer", team.id, 50)
        add_team_member(db, team.id, w1.id)
        add_team_member(db, team.id, w2.id)

        members = get_team_members_list(db, team.id)
        assert len(members) == 2
        worker_ids = {m.worker_id for m in members}
        assert w1.id in worker_ids
        assert w2.id in worker_ids

    def test_get_worker_team_memberships(self, db, worker):
        """Should get all team memberships for a worker."""
        team1 = create_team(db, "Engineering")
        team2 = create_team(db, "Platform")
        add_team_member(db, team1.id, worker.id)
        add_team_member(db, team2.id, worker.id)

        memberships = get_worker_team_memberships(db, worker.id)
        assert len(memberships) == 2
        team_ids = {m.team_id for m in memberships}
        assert team1.id in team_ids
        assert team2.id in team_ids

    def test_get_team_members_by_role(self, db, team):
        """Should get team members with a specific role."""
        w1 = create_worker(db, "Alice", "Developer", team.id, 50)
        w2 = create_worker(db, "Bob", "Lead", team.id, 60)
        w3 = create_worker(db, "Charlie", "Developer", team.id, 50)

        add_team_member(db, team.id, w1.id, role="member")
        add_team_member(db, team.id, w2.id, role="lead")
        add_team_member(db, team.id, w3.id, role="member")

        members = get_team_members_by_role(db, team.id, "member")
        assert len(members) == 2

        leads = get_team_members_by_role(db, team.id, "lead")
        assert len(leads) == 1
        assert leads[0].worker_id == w2.id


class TestPermissionQueries:
    """Test permission CRUD operations."""

    def test_grant_permission_to_worker(self, db, worker):
        """Should grant a permission to a worker."""
        perm = grant_permission(
            db,
            grantee_type="worker",
            grantee_id=worker.id,
            level=3,
            bead_id="bead-123",
            granted_by="admin-1",
        )
        assert perm.grantee_type == "worker"
        assert perm.grantee_id == worker.id
        assert perm.level == 3
        assert perm.bead_id == "bead-123"
        assert perm.granted_by == "admin-1"

    def test_grant_permission_to_team(self, db, team):
        """Should grant a permission to a team."""
        perm = grant_permission(
            db,
            grantee_type="team",
            grantee_id=team.id,
            level=1,
            bead_id="bead-456",
        )
        assert perm.grantee_type == "team"
        assert perm.grantee_id == team.id
        assert perm.level == 1

    def test_grant_global_permission(self, db, worker):
        """Should grant a global permission (no bead_id)."""
        perm = grant_permission(
            db,
            grantee_type="worker",
            grantee_id=worker.id,
            level=5,
        )
        assert perm.bead_id is None
        assert perm.level == 5

    def test_get_permission(self, db, worker):
        """Should get a permission by ID."""
        created = grant_permission(
            db, grantee_type="worker", grantee_id=worker.id, level=3
        )
        fetched = get_permission(db, created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.level == 3

    def test_get_permission_not_found(self, db):
        """Should return None for missing permission."""
        result = get_permission(db, "nonexistent")
        assert result is None

    def test_get_permission_for_grantee(self, db, worker):
        """Should get permission for a specific grantee on a bead."""
        grant_permission(
            db,
            grantee_type="worker",
            grantee_id=worker.id,
            level=3,
            bead_id="bead-123",
        )
        perm = get_permission_for_grantee(db, "bead-123", "worker", worker.id)
        assert perm is not None
        assert perm.level == 3

    def test_get_permission_for_grantee_global(self, db, worker):
        """Should get global permission for a grantee."""
        grant_permission(
            db,
            grantee_type="worker",
            grantee_id=worker.id,
            level=5,
            bead_id=None,
        )
        perm = get_permission_for_grantee(db, None, "worker", worker.id)
        assert perm is not None
        assert perm.level == 5

    def test_revoke_permission(self, db, worker):
        """Should revoke a permission by ID."""
        perm = grant_permission(
            db, grantee_type="worker", grantee_id=worker.id, level=3
        )
        result = revoke_permission(db, perm.id)
        assert result is True
        assert get_permission(db, perm.id) is None

    def test_revoke_permission_not_found(self, db):
        """Should return False when revoking non-existent permission."""
        result = revoke_permission(db, "nonexistent")
        assert result is False

    def test_revoke_permission_for_grantee(self, db, worker):
        """Should revoke permission for a specific grantee on a bead."""
        grant_permission(
            db,
            grantee_type="worker",
            grantee_id=worker.id,
            level=3,
            bead_id="bead-123",
        )
        result = revoke_permission_for_grantee(db, "bead-123", "worker", worker.id)
        assert result is True
        assert get_permission_for_grantee(db, "bead-123", "worker", worker.id) is None

    def test_get_permissions_for_bead(self, db, team, worker):
        """Should get all permissions for a bead."""
        grant_permission(
            db,
            grantee_type="worker",
            grantee_id=worker.id,
            level=3,
            bead_id="bead-123",
        )
        grant_permission(
            db,
            grantee_type="team",
            grantee_id=team.id,
            level=1,
            bead_id="bead-123",
        )
        perms = get_permissions_for_bead(db, "bead-123")
        assert len(perms) == 2

    def test_get_permissions_for_worker(self, db, worker):
        """Should get all direct permissions for a worker."""
        grant_permission(
            db, grantee_type="worker", grantee_id=worker.id, level=3, bead_id="bead-1"
        )
        grant_permission(
            db, grantee_type="worker", grantee_id=worker.id, level=1, bead_id="bead-2"
        )
        perms = get_permissions_for_worker(db, worker.id)
        assert len(perms) == 2

    def test_get_permissions_for_team(self, db, team):
        """Should get all permissions for a team."""
        grant_permission(
            db, grantee_type="team", grantee_id=team.id, level=2, bead_id="bead-1"
        )
        grant_permission(
            db, grantee_type="team", grantee_id=team.id, level=1, bead_id="bead-2"
        )
        perms = get_permissions_for_team(db, team.id)
        assert len(perms) == 2


class TestEffectivePermissionQueries:
    """Test effective permission CRUD operations."""

    def test_set_effective_permission(self, db, worker):
        """Should set effective permission for a worker on a bead."""
        eff = set_effective_permission(db, worker.id, "bead-123", level=3)
        assert eff.worker_id == worker.id
        assert eff.bead_id == "bead-123"
        assert eff.level == 3
        assert eff.computed_at is not None

    def test_get_effective_permission(self, db, worker):
        """Should get effective permission for a worker on a bead."""
        set_effective_permission(db, worker.id, "bead-123", level=4)
        eff = get_effective_permission(db, worker.id, "bead-123")
        assert eff is not None
        assert eff.level == 4

    def test_get_effective_permission_not_found(self, db, worker):
        """Should return None for missing effective permission."""
        result = get_effective_permission(db, worker.id, "bead-123")
        assert result is None

    def test_update_effective_permission(self, db, worker):
        """Should update effective permission (INSERT OR REPLACE)."""
        set_effective_permission(db, worker.id, "bead-123", level=1)
        set_effective_permission(db, worker.id, "bead-123", level=5)
        eff = get_effective_permission(db, worker.id, "bead-123")
        assert eff.level == 5

    def test_delete_effective_permission(self, db, worker):
        """Should delete effective permission for a worker on a bead."""
        set_effective_permission(db, worker.id, "bead-123", level=3)
        result = delete_effective_permission(db, worker.id, "bead-123")
        assert result is True
        assert get_effective_permission(db, worker.id, "bead-123") is None

    def test_delete_effective_permission_not_found(self, db, worker):
        """Should return False when deleting non-existent effective permission."""
        result = delete_effective_permission(db, worker.id, "bead-123")
        assert result is False

    def test_delete_effective_permissions_for_bead(self, db, team):
        """Should delete all effective permissions for a bead."""
        w1 = create_worker(db, "Alice", "Developer", team.id, 50)
        w2 = create_worker(db, "Bob", "Developer", team.id, 50)
        set_effective_permission(db, w1.id, "bead-123", level=3)
        set_effective_permission(db, w2.id, "bead-123", level=2)

        count = delete_effective_permissions_for_bead(db, "bead-123")
        assert count == 2
        assert get_effective_permission(db, w1.id, "bead-123") is None
        assert get_effective_permission(db, w2.id, "bead-123") is None


class TestPermissionAuditQueries:
    """Test permission audit logging operations."""

    def test_log_permission_audit(self, db, worker):
        """Should log a permission audit entry."""
        audit = log_permission_audit(
            db,
            action="grant",
            bead_id="bead-123",
            worker_id=worker.id,
            level=3,
            details='{"reason": "project access"}',
        )
        assert audit.action == "grant"
        assert audit.bead_id == "bead-123"
        assert audit.worker_id == worker.id
        assert audit.level == 3
        assert audit.details == '{"reason": "project access"}'
        assert audit.created_at is not None

    def test_log_permission_denial(self, db, worker):
        """Should log a permission denial."""
        audit = log_permission_audit(
            db,
            action="deny",
            bead_id="bead-123",
            worker_id=worker.id,
            level=3,
            details='{"required": "write", "actual": "read"}',
        )
        assert audit.action == "deny"

    def test_get_permission_audit_for_bead(self, db, worker):
        """Should get audit log entries for a bead."""
        log_permission_audit(db, "grant", "bead-123", worker.id, level=3)
        log_permission_audit(db, "check", "bead-123", worker.id, level=1)
        log_permission_audit(db, "deny", "bead-456", worker.id, level=3)

        audits = get_permission_audit_for_bead(db, "bead-123")
        assert len(audits) == 2

    def test_get_permission_audit_for_worker(self, db, worker):
        """Should get audit log entries for a worker."""
        other_worker = create_worker(
            db, "Bob", "Developer", worker.team_id, 50
        )
        log_permission_audit(db, "grant", "bead-123", worker.id, level=3)
        log_permission_audit(db, "grant", "bead-456", worker.id, level=2)
        log_permission_audit(db, "grant", "bead-789", other_worker.id, level=1)

        audits = get_permission_audit_for_worker(db, worker.id)
        assert len(audits) == 2

    def test_get_permission_denials(self, db, worker):
        """Should get recent permission denials."""
        log_permission_audit(db, "grant", "bead-123", worker.id, level=3)
        log_permission_audit(db, "deny", "bead-456", worker.id, level=3)
        log_permission_audit(db, "deny", "bead-789", worker.id, level=5)

        denials = get_permission_denials(db)
        assert len(denials) == 2
        for denial in denials:
            assert denial.action == "deny"

    def test_get_permission_audit_pagination(self, db, worker):
        """Should support pagination for audit log."""
        for i in range(10):
            log_permission_audit(db, "check", f"bead-{i}", worker.id, level=1)

        page1 = get_permission_audit_for_worker(db, worker.id, limit=5, offset=0)
        page2 = get_permission_audit_for_worker(db, worker.id, limit=5, offset=5)

        assert len(page1) == 5
        assert len(page2) == 5
        # Pages should have different entries
        page1_ids = {a.id for a in page1}
        page2_ids = {a.id for a in page2}
        assert page1_ids.isdisjoint(page2_ids)

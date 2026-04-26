"""
Tests for BeadService.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cli.core.db import init_database
from cli.core.queries import create_team, create_worker, grant_permission
from cli.core.permissions import PermissionLevel, PermissionDenied
from cli.core.bead_service import BeadService, BeadResult
from cli.core.constants import GRANTEE_TYPE_WORKER, BEAD_TYPE_TASK, BEAD_TYPE_BUG


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


@pytest.fixture
def service(db):
    """Create a BeadService instance."""
    return BeadService(db, bd_path="bd")


class TestBeadServicePermissions:
    """Test permission enforcement in BeadService."""

    def test_get_bead_requires_read_permission(self, service, worker):
        """Should raise PermissionDenied when worker lacks READ permission."""
        with pytest.raises(PermissionDenied) as exc_info:
            service.get_bead(worker.id, "bead-123")

        assert exc_info.value.required == PermissionLevel.READ
        assert exc_info.value.action == "get_bead"

    def test_get_bead_allowed_with_read_permission(self, db, service, worker):
        """Should allow get_bead when worker has READ permission."""
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.READ,
            bead_id="bead-123",
        )

        with patch.object(service, "_run_bd") as mock_run:
            mock_run.return_value = BeadResult(success=True, data="bead data")

            result = service.get_bead(worker.id, "bead-123")

            assert result.success
            mock_run.assert_called_once()

    def test_update_bead_requires_write_permission(self, db, service, worker):
        """Should raise PermissionDenied when worker lacks WRITE permission."""
        # Grant READ but not WRITE
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.READ,
            bead_id="bead-123",
        )

        with pytest.raises(PermissionDenied) as exc_info:
            service.update_bead(worker.id, "bead-123", status="in_progress")

        assert exc_info.value.required == PermissionLevel.WRITE
        assert exc_info.value.action == "update_bead"

    def test_update_bead_allowed_with_write_permission(self, db, service, worker):
        """Should allow update_bead when worker has WRITE permission."""
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.WRITE,
            bead_id="bead-123",
        )

        with patch.object(service, "_run_bd") as mock_run:
            mock_run.return_value = BeadResult(success=True, data="updated")

            result = service.update_bead(worker.id, "bead-123", status="in_progress")

            assert result.success
            mock_run.assert_called_once()

    def test_close_bead_requires_approve_permission(self, db, service, worker):
        """Should raise PermissionDenied when worker lacks APPROVE permission."""
        # Grant WRITE but not APPROVE
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.WRITE,
            bead_id="bead-123",
        )

        with pytest.raises(PermissionDenied) as exc_info:
            service.close_bead(worker.id, "bead-123")

        assert exc_info.value.required == PermissionLevel.APPROVE
        assert exc_info.value.action == "close_bead"

    def test_close_bead_allowed_with_approve_permission(self, db, service, worker):
        """Should allow close_bead when worker has APPROVE permission."""
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.APPROVE,
            bead_id="bead-123",
        )

        with patch.object(service, "_run_bd") as mock_run:
            mock_run.return_value = BeadResult(success=True, data="closed")

            result = service.close_bead(worker.id, "bead-123", reason="done")

            assert result.success
            mock_run.assert_called_once()

    def test_add_comment_requires_comment_permission(self, service, worker):
        """Should raise PermissionDenied when worker lacks COMMENT permission."""
        with pytest.raises(PermissionDenied) as exc_info:
            service.add_comment(worker.id, "bead-123", "my comment")

        assert exc_info.value.required == PermissionLevel.COMMENT
        assert exc_info.value.action == "add_comment"

    def test_delete_bead_requires_admin_permission(self, db, service, worker):
        """Should raise PermissionDenied when worker lacks ADMIN permission."""
        # Grant APPROVE but not ADMIN
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.APPROVE,
            bead_id="bead-123",
        )

        with pytest.raises(PermissionDenied) as exc_info:
            service.delete_bead(worker.id, "bead-123")

        assert exc_info.value.required == PermissionLevel.ADMIN
        assert exc_info.value.action == "delete_bead"

    def test_add_dependency_requires_write_permission(self, service, worker):
        """Should raise PermissionDenied when worker lacks WRITE permission."""
        with pytest.raises(PermissionDenied) as exc_info:
            service.add_dependency(worker.id, "bead-123", "bead-456")

        assert exc_info.value.required == PermissionLevel.WRITE
        assert exc_info.value.action == "add_dependency"


class TestBeadServiceOperations:
    """Test BeadService operations."""

    def test_create_bead_no_permission_required(self, service, worker):
        """Should allow create_bead without prior permission."""
        with patch.object(service, "_run_bd") as mock_run:
            mock_run.return_value = BeadResult(success=True, data="bead-new")

            result = service.create_bead(
                worker.id,
                title="New Task",
                bead_type=BEAD_TYPE_TASK,
                priority=2,
            )

            assert result.success
            mock_run.assert_called_once()

    def test_list_beads_no_permission_required(self, service, worker):
        """Should allow list_beads without specific permission."""
        with patch.object(service, "_run_bd") as mock_run:
            mock_run.return_value = BeadResult(success=True, data="bead-1\nbead-2")

            result = service.list_beads(worker.id, status="open")

            assert result.success
            mock_run.assert_called_once()

    def test_get_permission_level(self, db, service, worker):
        """Should return worker's permission level on bead."""
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.WRITE,
            bead_id="bead-123",
        )

        level = service.get_permission_level(worker.id, "bead-123")

        assert level == PermissionLevel.WRITE

    def test_can_access_true(self, db, service, worker):
        """Should return True when worker has permission."""
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.READ,
            bead_id="bead-123",
        )

        assert service.can_access(worker.id, "bead-123", PermissionLevel.READ)

    def test_can_access_false(self, service, worker):
        """Should return False when worker lacks permission."""
        assert not service.can_access(worker.id, "bead-123", PermissionLevel.READ)


class TestBeadServiceBdCommands:
    """Test bd command building."""

    def test_update_bead_builds_correct_command(self, db, service, worker):
        """Should build correct bd command for update."""
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.WRITE,
            bead_id="bead-123",
        )

        with patch.object(service, "_run_bd") as mock_run:
            mock_run.return_value = BeadResult(success=True)

            service.update_bead(
                worker.id,
                "bead-123",
                status="closed",
                priority=1,
                assignee="bob",
            )

            mock_run.assert_called_once_with(
                "update", "bead-123",
                "--status", "closed",
                "--priority", "1",
                "--assignee", "bob",
                worker_id=worker.id,
            )

    def test_create_bead_builds_correct_command(self, service, worker):
        """Should build correct bd command for create."""
        with patch.object(service, "_run_bd") as mock_run:
            mock_run.return_value = BeadResult(success=True, data="bead-new")

            service.create_bead(
                worker.id,
                title="Test Task",
                bead_type=BEAD_TYPE_BUG,
                priority=0,
                description="Fix this",
                parent="bead-parent",
            )

            mock_run.assert_called_once_with(
                "create",
                "--title", "Test Task",
                "--type", "bug",
                "--priority", "0",
                "--description", "Fix this",
                "--parent", "bead-parent",
                worker_id=worker.id,
            )

    def test_close_bead_with_reason(self, db, service, worker):
        """Should include reason in close command."""
        grant_permission(
            db,
            grantee_type=GRANTEE_TYPE_WORKER,
            grantee_id=worker.id,
            level=PermissionLevel.APPROVE,
            bead_id="bead-123",
        )

        with patch.object(service, "_run_bd") as mock_run:
            mock_run.return_value = BeadResult(success=True)

            service.close_bead(worker.id, "bead-123", reason="Completed")

            mock_run.assert_called_once_with(
                "close", "bead-123",
                "--reason", "Completed",
                worker_id=worker.id,
            )

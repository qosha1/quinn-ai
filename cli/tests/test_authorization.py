"""
Unit tests for authorization system.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest

from core.db import init_database
from core.queries import create_team, create_worker
from core.authorization import AuthorizationManager


@pytest.fixture
def tmpdir_path():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db(tmpdir_path):
    """Create test database."""
    db_path = tmpdir_path / "quinn.db"
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def team(db):
    """Create test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def ceo(db, team):
    """Create CEO worker."""
    return create_worker(db, "CEO", "CEO", team.id, 100)


@pytest.fixture
def director(db, team, ceo):
    """Create director worker."""
    worker_data = create_worker(db, "Director", "Director", team.id, 80)
    # Set CEO as manager
    db.execute(
        "UPDATE workers SET manager_id = ? WHERE id = ?",
        (ceo.id, worker_data.id)
    )
    return worker_data


@pytest.fixture
def developer(db, team, director):
    """Create developer worker."""
    worker_data = create_worker(db, "Developer", "Engineer", team.id, 50)
    # Set director as manager
    db.execute(
        "UPDATE workers SET manager_id = ? WHERE id = ?",
        (director.id, worker_data.id)
    )
    return worker_data


class TestCanFire:
    """Test firing authorization with critical work checks."""

    def test_ceo_can_fire_direct_report(self, db, tmpdir_path, ceo, director):
        """CEO can fire direct reports when no critical work."""
        auth = AuthorizationManager(db, tmpdir_path)

        with patch("cli.core.bd_wrapper.run_bd") as mock_bd:
            # Mock: no active beads
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "[]"
            mock_bd.return_value = mock_result

            result = auth.can(ceo.id, "fire", director.id)

            assert result.allowed
            assert "authorized to fire" in result.reason

    def test_cannot_fire_worker_with_active_work(self, db, tmpdir_path, ceo, director):
        """Cannot fire worker who has active work in progress."""
        auth = AuthorizationManager(db, tmpdir_path)

        with patch("cli.core.bd_wrapper.run_bd") as mock_bd:
            # Mock: worker has active beads
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '[{"id": "quinnai-123", "status": "in_progress"}]'
            mock_bd.return_value = mock_result

            result = auth.can(ceo.id, "fire", director.id)

            assert not result.allowed
            assert "active work" in result.reason.lower()
            assert "quinnai-123" in result.reason

    def test_cannot_fire_non_direct_report(self, db, tmpdir_path, ceo, director, developer):
        """Director cannot fire workers who aren't direct reports."""
        auth = AuthorizationManager(db, tmpdir_path)

        # Try to fire CEO (director's manager, not a direct report)
        result = auth.can(director.id, "fire", ceo.id)

        assert not result.allowed
        assert "not a direct report" in result.reason

    def test_non_director_cannot_fire(self, db, tmpdir_path, developer, director):
        """Non-director/CEO workers cannot fire anyone."""
        auth = AuthorizationManager(db, tmpdir_path)

        result = auth.can(developer.id, "fire", director.id)

        assert not result.allowed
        assert "does not have firing authority" in result.reason

    def test_fire_fails_gracefully_on_bead_error(self, db, tmpdir_path, ceo, director):
        """Firing allowed if bead query fails (fail open)."""
        auth = AuthorizationManager(db, tmpdir_path)

        with patch("cli.core.bd_wrapper.run_bd") as mock_bd:
            # Mock: bd command fails
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_bd.return_value = mock_result

            result = auth.can(ceo.id, "fire", director.id)

            # Should allow firing despite error (fail open for safety)
            assert result.allowed

    def test_fire_allowed_with_multiple_active_beads(self, db, tmpdir_path, ceo, director):
        """Shows multiple bead IDs in denial message."""
        auth = AuthorizationManager(db, tmpdir_path)

        with patch("cli.core.bd_wrapper.run_bd") as mock_bd:
            # Mock: multiple active beads
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '''[
                {"id": "quinnai-123", "status": "in_progress"},
                {"id": "quinnai-456", "status": "in_progress"},
                {"id": "quinnai-789", "status": "in_progress"}
            ]'''
            mock_bd.return_value = mock_result

            result = auth.can(ceo.id, "fire", director.id)

            assert not result.allowed
            assert "3 active work item(s)" in result.reason
            assert "quinnai-123" in result.reason

    def test_fire_with_no_org_path_setting(self, db, tmpdir_path, ceo, director):
        """Firing allowed if org_path not provided."""
        # Pass None for org_path - can't check beads
        auth = AuthorizationManager(db, None)

        result = auth.can(ceo.id, "fire", director.id)

        # Should allow firing when can't check beads
        assert result.allowed


class TestHasCriticalWork:
    """Test the _has_critical_work helper method."""

    def test_returns_false_when_no_active_work(self, db, tmpdir_path, developer):
        """Returns false when worker has no active beads."""
        auth = AuthorizationManager(db, tmpdir_path)

        with patch("cli.core.bd_wrapper.run_bd") as mock_bd:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "[]"
            mock_bd.return_value = mock_result

            has_work, details = auth._has_critical_work(developer.id)

            assert not has_work
            assert details is None

    def test_returns_true_with_work_details(self, db, tmpdir_path, developer):
        """Returns true with details when worker has active work."""
        auth = AuthorizationManager(db, tmpdir_path)

        with patch("cli.core.bd_wrapper.run_bd") as mock_bd:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '[{"id": "quinnai-999", "status": "in_progress"}]'
            mock_bd.return_value = mock_result

            has_work, details = auth._has_critical_work(developer.id)

            assert has_work
            assert "1 active work item(s)" in details
            assert "quinnai-999" in details

    def test_handles_bd_command_failure(self, db, tmpdir_path, developer):
        """Handles bd command failure gracefully."""
        auth = AuthorizationManager(db, tmpdir_path)

        with patch("cli.core.bd_wrapper.run_bd") as mock_bd:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_bd.return_value = mock_result

            has_work, details = auth._has_critical_work(developer.id)

            # Fail open - no critical work detected on error
            assert not has_work
            assert details is None

    def test_handles_json_parse_error(self, db, tmpdir_path, developer):
        """Handles invalid JSON output gracefully."""
        auth = AuthorizationManager(db, tmpdir_path)

        with patch("cli.core.bd_wrapper.run_bd") as mock_bd:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "invalid json"
            mock_bd.return_value = mock_result

            has_work, details = auth._has_critical_work(developer.id)

            # Should handle parse error and fail open
            assert not has_work
            assert details is None

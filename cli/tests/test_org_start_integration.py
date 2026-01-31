"""Tests for org start sequence.

After architecture changes (quinnai-3gqq), org.start() is now a pure state transition.
Session spawning is handled separately by CLI commands. Monitor services are managed
by Board UI only (they die when CLI exits anyway).

This file tests:
1. Core org.start() state transitions
2. Org path derivation
3. State persistence
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from core.org import Org
from core.db import init_database
from core.session import SessionConfig
from shared import InvalidOrgTransition
from shared.enums import OrgStatus


@pytest.fixture
def temp_org_dir():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / "live").mkdir(parents=True)
        (org_path / "config").mkdir(parents=True)
        (org_path / "storage" / "workers").mkdir(parents=True)
        (org_path / "storage" / "shared").mkdir(parents=True)
        (org_path / ".beads").mkdir(parents=True)
        yield org_path


@pytest.fixture
def test_db(temp_org_dir):
    """Create a test database."""
    db_path = temp_org_dir / "live" / "quinn.db"
    db = init_database(db_path)
    yield db
    db.close()


@pytest.fixture
def initialized_org(test_db, temp_org_dir):
    """Create an initialized org with CEO."""
    org = Org(test_db, temp_org_dir)
    ceo = org.init("TestCEO", "CEO")
    return org


class TestOrgStartStateTransition:
    """Test that org.start() performs correct state transition."""

    def test_start_transitions_from_initialized_to_running(self, initialized_org):
        """Start from initialized should transition to running."""
        old_status, new_status = initialized_org.start()

        assert old_status == OrgStatus.INITIALIZED.value
        assert new_status == OrgStatus.RUNNING.value
        assert initialized_org.status == OrgStatus.RUNNING.value

    def test_start_activates_ceo_worker(self, initialized_org):
        """Start should activate CEO worker (complete onboarding)."""
        # Before start, CEO is pending
        assert initialized_org.ceo.lifecycle_status == "pending"

        initialized_org.start()

        # After start, CEO is active
        assert initialized_org.ceo.lifecycle_status == "active"

    def test_start_from_stopped_resumes(self, initialized_org):
        """Start from stopped should resume to running."""
        # First start
        initialized_org.start()
        assert initialized_org.status == OrgStatus.RUNNING.value

        # Stop
        initialized_org.stop()
        assert initialized_org.status == OrgStatus.STOPPED.value

        # Resume
        old_status, new_status = initialized_org.start()
        assert old_status == OrgStatus.STOPPED.value
        assert new_status == OrgStatus.RUNNING.value

    def test_start_when_running_raises_error(self, initialized_org):
        """Start when already running should raise error."""
        initialized_org.start()

        with pytest.raises(InvalidOrgTransition) as exc_info:
            initialized_org.start()

        assert exc_info.value.current == "running"
        assert exc_info.value.attempted == "running"

    def test_start_from_uninitialized_raises_error(self, test_db, temp_org_dir):
        """Start from uninitialized should raise error."""
        org = Org(test_db, temp_org_dir)
        # Don't init, so it's uninitialized

        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.start()

        assert exc_info.value.current == "uninitialized"


class TestOrgStartDoesNotStartMonitors:
    """Verify that org.start() does NOT start monitoring services.

    Per quinnai-3gqq: Monitors die when CLI exits, so they're ineffective.
    Only Board UI should manage monitors since it has persistent lifecycle.
    """

    @patch('core.escalation_monitor.EscalationMonitor')
    def test_start_does_not_create_escalation_monitor(self, mock_monitor_class, initialized_org):
        """org.start() should NOT create escalation monitor."""
        initialized_org.start()

        # Monitor class should NOT be instantiated
        mock_monitor_class.assert_not_called()

    @patch('core.session_capture.SessionCaptureService')
    def test_start_does_not_create_session_capture(self, mock_capture_class, initialized_org):
        """org.start() should NOT create session capture service."""
        initialized_org.start()

        # Capture service should NOT be instantiated
        mock_capture_class.assert_not_called()

    @patch('core.activity_reporter.ActivityReporter')
    def test_start_does_not_create_activity_reporter(self, mock_reporter_class, initialized_org):
        """org.start() should NOT create activity reporter."""
        initialized_org.start()

        # Activity reporter should NOT be instantiated
        mock_reporter_class.assert_not_called()


class TestOrgRollback:
    """Test org rollback functionality."""

    def test_rollback_to_status_changes_state(self, initialized_org):
        """rollback_to_status should change org state."""
        initialized_org.start()
        assert initialized_org.status == OrgStatus.RUNNING.value

        initialized_org.rollback_to_status(OrgStatus.INITIALIZED.value)
        assert initialized_org.status == OrgStatus.INITIALIZED.value

    def test_rollback_from_running_to_stopped(self, initialized_org):
        """Should be able to rollback from running to stopped."""
        initialized_org.start()
        initialized_org.stop()
        initialized_org.start()
        assert initialized_org.status == OrgStatus.RUNNING.value

        initialized_org.rollback_to_status(OrgStatus.STOPPED.value)
        assert initialized_org.status == OrgStatus.STOPPED.value


class TestOrgPathDerivation:
    """Test org_path property derivation."""

    def test_org_path_property(self, initialized_org, temp_org_dir):
        """org_path property should return correct path."""
        assert initialized_org.org_path == temp_org_dir

    def test_org_derives_path_from_db(self, test_db, temp_org_dir):
        """Org should derive path from database when not explicitly provided."""
        org = Org(test_db)  # No org_path provided

        # Should derive from db_path (live/quinn.db -> parent.parent)
        assert org.org_path == temp_org_dir


class TestOrgStopWithMonitors:
    """Test that org.stop() cleans up any active monitors."""

    @patch('core.escalation_monitor.EscalationMonitor')
    def test_stop_handles_monitor_cleanup_gracefully(self, mock_monitor_class, initialized_org):
        """stop() should attempt to clean up monitors even if not started by CLI."""
        initialized_org.start()

        # Stop should complete without error even with no monitors running
        initialized_org.stop()
        assert initialized_org.status == OrgStatus.STOPPED.value

    def test_stop_preserves_ceo_lifecycle_status(self, initialized_org):
        """stop() should preserve CEO lifecycle status."""
        initialized_org.start()
        assert initialized_org.ceo.lifecycle_status == "active"

        initialized_org.stop()

        # CEO remains active (only runtime changes, not lifecycle)
        assert initialized_org.ceo.lifecycle_status == "active"


class TestOrgStartReturnsStatusPair:
    """Test that start() returns old/new status for rollback support."""

    def test_start_returns_old_and_new_status(self, initialized_org):
        """start() should return (old_status, new_status) tuple."""
        result = initialized_org.start()

        assert isinstance(result, tuple)
        assert len(result) == 2
        old_status, new_status = result
        assert old_status == OrgStatus.INITIALIZED.value
        assert new_status == OrgStatus.RUNNING.value

    def test_resume_returns_old_and_new_status(self, initialized_org):
        """Resume should also return status tuple."""
        initialized_org.start()
        initialized_org.stop()

        old_status, new_status = initialized_org.start()

        assert old_status == OrgStatus.STOPPED.value
        assert new_status == OrgStatus.RUNNING.value

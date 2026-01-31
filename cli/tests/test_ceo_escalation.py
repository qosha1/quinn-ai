"""Tests for CEO escalation helper.

Tests verify that CEO escalations include comprehensive org context
and correctly map urgency levels to notification priorities.
"""

import pytest

from cli.core.ceo_escalation import (
    CEOEscalationHelper,
    EscalationUrgency,
    OrgStateContext,
)
from cli.core.notifications import NotificationPriority
from cli.core.db import init_database
from pathlib import Path
import tempfile


class TestOrgStateContext:
    """Tests for OrgStateContext dataclass."""

    def test_create_org_state_context(self):
        """Test creating org state context."""
        context = OrgStateContext(
            total_workers=5,
            active_workers=3,
            idle_workers=1,
            blocked_workers=1,
            total_work_items=10,
            blocked_work_items=2,
            okr_count=3,
            recent_escalations=1,
        )

        assert context.total_workers == 5
        assert context.active_workers == 3
        assert context.okr_count == 3


class TestCEOEscalationHelper:
    """Tests for CEO escalation helper."""

    @pytest.fixture
    def db(self):
        """Create test database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        db = init_database(db_path)

        # Add test team first
        with db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO teams (id, name)
                VALUES ('team-1', 'Engineering')
                """
            )

        # Add test workers
        with db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO workers (id, name, role, team_id, status, cost)
                VALUES ('ceo', 'CEO', 'ceo', 'team-1', 'active', 100)
                """
            )
            cursor.execute(
                """
                INSERT INTO workers (id, name, role, team_id, status, cost)
                VALUES ('worker-1', 'Worker 1', 'engineer', 'team-1', 'active', 50)
                """
            )

        yield db

        db.close()
        db_path.unlink()

    @pytest.fixture
    def helper(self, db):
        """Create CEO escalation helper."""
        return CEOEscalationHelper(db, "test-org")

    def test_gather_org_state(self, helper):
        """Test gathering org state from database."""
        state = helper.gather_org_state()

        assert state.total_workers == 2  # CEO + worker
        assert state.active_workers == 2

    def test_determine_urgency_no_okrs(self, helper):
        """Test urgency determination when no OKRs exist."""
        state = OrgStateContext(
            total_workers=5,
            active_workers=3,
            idle_workers=2,
            blocked_workers=0,
            total_work_items=10,
            blocked_work_items=0,
            okr_count=0,  # No OKRs!
            recent_escalations=0,
        )

        urgency = helper.determine_urgency(state)

        # No OKRs = URGENT
        assert urgency == EscalationUrgency.URGENT

    def test_determine_urgency_many_blocked(self, helper):
        """Test urgency determination when many items blocked."""
        state = OrgStateContext(
            total_workers=5,
            active_workers=3,
            idle_workers=1,
            blocked_workers=1,
            total_work_items=10,
            blocked_work_items=6,  # 60% blocked!
            okr_count=3,
            recent_escalations=0,
        )

        urgency = helper.determine_urgency(state)

        # > 50% blocked = URGENT
        assert urgency == EscalationUrgency.URGENT

    def test_determine_urgency_many_idle(self, helper):
        """Test urgency determination when many workers idle."""
        state = OrgStateContext(
            total_workers=5,
            active_workers=1,
            idle_workers=4,  # Most workers idle!
            blocked_workers=0,
            total_work_items=10,
            blocked_work_items=0,
            okr_count=3,
            recent_escalations=0,
        )

        urgency = helper.determine_urgency(state)

        # More idle than active = WARNING
        assert urgency == EscalationUrgency.WARNING

    def test_determine_urgency_healthy_org(self, helper):
        """Test urgency determination for healthy org."""
        state = OrgStateContext(
            total_workers=5,
            active_workers=4,
            idle_workers=1,
            blocked_workers=0,
            total_work_items=10,
            blocked_work_items=1,
            okr_count=3,
            recent_escalations=0,
        )

        urgency = helper.determine_urgency(state)

        # Healthy org = INFO
        assert urgency == EscalationUrgency.INFO

    def test_explicit_urgency_override(self, helper):
        """Test that explicit urgency overrides auto-detection."""
        state = OrgStateContext(
            total_workers=5,
            active_workers=4,
            idle_workers=1,
            blocked_workers=0,
            total_work_items=10,
            blocked_work_items=0,
            okr_count=3,
            recent_escalations=0,
        )

        # Explicitly request URGENT despite healthy org
        urgency = helper.determine_urgency(state, EscalationUrgency.URGENT)

        assert urgency == EscalationUrgency.URGENT

    def test_format_escalation_message(self, helper):
        """Test formatting escalation message with org context."""
        state = OrgStateContext(
            total_workers=5,
            active_workers=3,
            idle_workers=1,
            blocked_workers=1,
            total_work_items=10,
            blocked_work_items=2,
            okr_count=0,
            recent_escalations=0,
        )

        message, context = helper.format_escalation_message(
            issue="No clear direction for team",
            org_state=state,
            urgency=EscalationUrgency.URGENT,
            attempts_made=["Reviewed existing work", "Checked OKRs"],
            specific_question="What should we prioritize this quarter?",
        )

        # Check message content
        assert "No clear direction for team" in message
        assert "Workers: 3/5 active" in message
        assert "Active OKRs: 0" in message
        assert "Reviewed existing work" in message
        assert "What should we prioritize" in message
        assert "🚨 Urgent" in message

        # Check context
        assert context["ceo_escalation"] is True
        assert context["urgency"] == "urgent"
        assert context["org_state"]["total_workers"] == 5
        assert context["org_state"]["okr_count"] == 0
        assert context["specific_question"] == "What should we prioritize this quarter?"

    def test_urgency_to_notification_priority(self, helper):
        """Test mapping urgency to notification priority."""
        assert (
            helper.urgency_to_notification_priority(EscalationUrgency.INFO)
            == NotificationPriority.INFO
        )
        assert (
            helper.urgency_to_notification_priority(EscalationUrgency.WARNING)
            == NotificationPriority.HIGH
        )
        assert (
            helper.urgency_to_notification_priority(EscalationUrgency.URGENT)
            == NotificationPriority.URGENT
        )

    def test_should_ceo_wait(self, helper):
        """Test CEO waiting behavior based on urgency."""
        # CEO should only wait on URGENT
        assert helper.should_ceo_wait(EscalationUrgency.URGENT) is True
        assert helper.should_ceo_wait(EscalationUrgency.WARNING) is False
        assert helper.should_ceo_wait(EscalationUrgency.INFO) is False

    def test_message_includes_suggested_actions(self, helper):
        """Test that message includes context-appropriate suggestions."""
        state_no_okrs = OrgStateContext(
            total_workers=5,
            active_workers=3,
            idle_workers=1,
            blocked_workers=0,
            total_work_items=10,
            blocked_work_items=0,
            okr_count=0,  # No OKRs
            recent_escalations=0,
        )

        message, _ = helper.format_escalation_message(
            issue="Need direction",
            org_state=state_no_okrs,
            urgency=EscalationUrgency.URGENT,
        )

        # Should suggest creating OKRs
        assert "Create OKRs" in message

        state_blocked = OrgStateContext(
            total_workers=5,
            active_workers=3,
            idle_workers=0,
            blocked_workers=2,
            total_work_items=10,
            blocked_work_items=5,  # Blocked work
            okr_count=3,
            recent_escalations=0,
        )

        message2, _ = helper.format_escalation_message(
            issue="Work blocked",
            org_state=state_blocked,
            urgency=EscalationUrgency.URGENT,
        )

        # Should suggest reviewing blocked work
        assert "blocked work" in message2.lower()

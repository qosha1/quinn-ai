"""Tests for interface contracts."""

import pytest
from datetime import datetime
from pathlib import Path

from board_ui.interfaces.org_connection import (
    OrgStatus,
    WorkerStatus,
    SessionState,
    WorkerInfo,
    OrgInfo,
    BudgetSummary,
    Message,
    OKRInfo,
)


class TestDataClasses:
    """Tests for interface data classes."""

    def test_worker_info_creation(self):
        """WorkerInfo should be creatable with required fields."""
        worker = WorkerInfo(
            id="worker-001",
            name="Alice",
            role="CEO",
            team_name="Executive",
            status=WorkerStatus.ACTIVE,
            session_state=SessionState.RUNNING,
            tmux_session_name="org-acme-alice",
            manager_id=None,
            is_ceo=True,
        )

        assert worker.id == "worker-001"
        assert worker.name == "Alice"
        assert worker.is_ceo is True
        assert worker.status == WorkerStatus.ACTIVE

    def test_org_info_creation(self):
        """OrgInfo should be creatable with required fields."""
        org = OrgInfo(
            path=Path("/tmp/test-org"),
            name="Test Org",
            status=OrgStatus.RUNNING,
            ceo_worker_id="worker-001",
            worker_count=5,
            active_session_count=3,
            started_at=datetime.now(),
            stopped_at=None,
        )

        assert org.name == "Test Org"
        assert org.status == OrgStatus.RUNNING
        assert org.worker_count == 5

    def test_budget_summary_creation(self):
        """BudgetSummary should be creatable with required fields."""
        now = datetime.now()
        budget = BudgetSummary(
            total_allocated=1000.0,
            total_spent=150.0,
            total_available=850.0,
            period_start=now,
            period_end=now,
            spend_today=25.0,
        )

        assert budget.total_allocated == 1000.0
        assert budget.total_available == 850.0
        assert budget.spend_today == 25.0

    def test_message_creation(self):
        """Message should be creatable with required fields."""
        msg = Message(
            id="msg-001",
            from_worker_id="worker-002",
            from_worker_name="Bob",
            channel_name="escalations",
            content="Need board approval for budget increase",
            priority=1,
            created_at=datetime.now(),
            requires_response=True,
        )

        assert msg.id == "msg-001"
        assert msg.priority == 1
        assert msg.requires_response is True
        assert msg.is_read is False  # Default

    def test_okr_info_creation(self):
        """OKRInfo should be creatable with required fields."""
        okr = OKRInfo(
            id="okr-001",
            title="Ship v1.0",
            description="Deliver the first version of the product",
            owner_name="Alice",
            owner_id="worker-001",
            status="active",
            parent_id=None,
            key_results=[
                {"metric": "Features complete", "target": 10, "current": 7, "unit": "count"},
                {"metric": "Test coverage", "target": 80, "current": 72, "unit": "percent"},
            ],
        )

        assert okr.title == "Ship v1.0"
        assert len(okr.key_results) == 2
        assert okr.key_results[0]["current"] == 7


class TestEnums:
    """Tests for status enums."""

    def test_org_status_values(self):
        """OrgStatus should have expected values."""
        assert OrgStatus.UNINITIALIZED.value == "uninitialized"
        assert OrgStatus.INITIALIZED.value == "initialized"
        assert OrgStatus.RUNNING.value == "running"
        assert OrgStatus.STOPPED.value == "stopped"

    def test_worker_status_values(self):
        """WorkerStatus should have expected values."""
        assert WorkerStatus.PENDING.value == "pending"
        assert WorkerStatus.ACTIVE.value == "active"
        assert WorkerStatus.TERMINATED.value == "terminated"

    def test_session_state_values(self):
        """SessionState should have expected values."""
        assert SessionState.STARTING.value == "starting"
        assert SessionState.RUNNING.value == "running"
        assert SessionState.CRASHED.value == "crashed"

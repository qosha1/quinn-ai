"""Tests for escalation notification handler integration.

Tests the bridge between the escalation system and board notifications,
verifying that escalation events trigger appropriate notifications.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from cli.core.notifications import (
    EscalationNotificationHandler,
    NotificationDispatcher,
    NotificationPriority,
    BoardNotification,
    NotificationResult,
)
from shared.escalation.manager import EscalationEntry, EscalationState


class TestEscalationNotificationHandler:
    """Tests for EscalationNotificationHandler."""

    @pytest.fixture
    def mock_dispatcher(self):
        """Create a mock notification dispatcher."""
        dispatcher = Mock(spec=NotificationDispatcher)
        dispatcher.dispatch = Mock(return_value={"test_channel": NotificationResult.SUCCESS})
        return dispatcher

    @pytest.fixture
    def handler(self, mock_dispatcher):
        """Create an escalation notification handler."""
        return EscalationNotificationHandler(mock_dispatcher)

    @pytest.fixture
    def sample_escalation(self):
        """Create a sample escalation entry."""
        return EscalationEntry(
            id="esc-001",
            worker_id="worker-123",
            issue="Need help with task ABC",
            context={"task_id": "task-abc", "urgency": "high"},
            state=EscalationState.PENDING,
            created_at=datetime.now(),
            current_target="manager-456",
            escalation_path=["manager-456", "ceo", "board"],
            attempts=1,
        )

    def test_notify_created_event(self, handler, mock_dispatcher, sample_escalation):
        """Test notification for 'created' event."""
        handler.notify(sample_escalation, "created")

        # Verify dispatcher was called
        assert mock_dispatcher.dispatch.called
        notification = mock_dispatcher.dispatch.call_args[0][0]

        # Check notification properties
        assert isinstance(notification, BoardNotification)
        assert notification.priority == NotificationPriority.NORMAL
        assert "New Escalation" in notification.title
        assert "worker-123" in notification.title
        assert "manager-456" in notification.message
        assert notification.worker_id == "worker-123"

        # Check metadata
        assert notification.metadata["escalation_id"] == "esc-001"
        assert notification.metadata["event_type"] == "created"
        assert notification.metadata["escalation_target"] == "manager-456"
        assert notification.metadata["escalation_path"] == ["manager-456", "ceo", "board"]

    def test_notify_timeout_event(self, handler, mock_dispatcher, sample_escalation):
        """Test notification for 'timeout' event."""
        handler.notify(sample_escalation, "timeout")

        notification = mock_dispatcher.dispatch.call_args[0][0]

        # Timeout should be high priority
        assert notification.priority == NotificationPriority.HIGH
        assert "Timeout" in notification.title
        assert "timed out" in notification.message

    def test_notify_resolved_event(self, handler, mock_dispatcher, sample_escalation):
        """Test notification for 'resolved' event."""
        from shared.escalation.interface import EscalationResponse

        sample_escalation.response = EscalationResponse(
            resolved=True,
            guidance="Here's how to proceed",
            escalated_to="manager-456",
        )

        handler.notify(sample_escalation, "resolved")

        notification = mock_dispatcher.dispatch.call_args[0][0]

        # Resolved should be info priority (good news)
        assert notification.priority == NotificationPriority.INFO
        assert "Resolved" in notification.title
        assert "resolved by manager-456" in notification.message

    def test_notify_failed_event(self, handler, mock_dispatcher, sample_escalation):
        """Test notification for 'failed' event."""
        sample_escalation.attempts = 3

        handler.notify(sample_escalation, "failed")

        notification = mock_dispatcher.dispatch.call_args[0][0]

        # Failed should be urgent priority
        assert notification.priority == NotificationPriority.URGENT
        assert "Failed" in notification.title
        assert "failed after 3 attempts" in notification.message
        assert "Board intervention" in notification.message

    def test_notify_unknown_event(self, handler, mock_dispatcher, sample_escalation):
        """Test notification for unknown event type."""
        handler.notify(sample_escalation, "unknown_event")

        notification = mock_dispatcher.dispatch.call_args[0][0]

        # Unknown event should use normal priority
        assert notification.priority == NotificationPriority.NORMAL
        assert "unknown_event" in notification.message

    def test_issue_truncation(self, handler, mock_dispatcher, sample_escalation):
        """Test that long issues are truncated in metadata."""
        long_issue = "A" * 300
        sample_escalation.issue = long_issue

        handler.notify(sample_escalation, "created")

        notification = mock_dispatcher.dispatch.call_args[0][0]

        # Metadata issue should be truncated to 200 chars
        assert len(notification.metadata["issue"]) == 200

    def test_dispatcher_failure_handling(self, handler, sample_escalation):
        """Test handling of dispatcher failures."""
        failing_dispatcher = Mock(spec=NotificationDispatcher)
        failing_dispatcher.dispatch = Mock(
            return_value={"channel1": NotificationResult.FAILED}
        )

        handler_with_failures = EscalationNotificationHandler(failing_dispatcher)

        # Should not raise exception on failure
        handler_with_failures.notify(sample_escalation, "created")

        # Dispatcher should have been called
        assert failing_dispatcher.dispatch.called


class TestEscalationManagerIntegration:
    """Tests for EscalationManager with notification handler."""

    @pytest.fixture
    def mock_dispatcher(self):
        """Create a mock notification dispatcher."""
        dispatcher = Mock(spec=NotificationDispatcher)
        dispatcher.dispatch = Mock(return_value={"test": NotificationResult.SUCCESS})
        return dispatcher

    @pytest.fixture
    def notification_handler(self, mock_dispatcher):
        """Create notification handler."""
        return EscalationNotificationHandler(mock_dispatcher)

    @pytest.fixture
    def escalation_manager(self, notification_handler):
        """Create escalation manager with notification handler."""
        from shared.escalation.manager import EscalationManager, EscalationConfig
        from shared.escalation.hierarchical import OrgTopology, WorkerNode

        # Build simple topology
        topology = OrgTopology()
        topology.add_node(WorkerNode("worker-1", "Worker 1", "manager-1", is_manager=False))
        topology.add_node(WorkerNode("manager-1", "Manager 1", "ceo", is_manager=True))
        topology.add_node(WorkerNode("ceo", "CEO", None, is_manager=True))

        config = EscalationConfig(timeout_seconds=60)

        return EscalationManager(topology, config, notification_handler)

    def test_submit_triggers_created_notification(
        self, escalation_manager, mock_dispatcher
    ):
        """Test that submitting escalation triggers 'created' notification."""
        escalation_manager.submit("worker-1", "Need help")

        # Verify notification was dispatched
        assert mock_dispatcher.dispatch.called
        notification = mock_dispatcher.dispatch.call_args[0][0]

        assert "New Escalation" in notification.title
        assert notification.metadata["event_type"] == "created"

    def test_resolution_triggers_resolved_notification(
        self, escalation_manager, mock_dispatcher
    ):
        """Test that resolving escalation triggers 'resolved' notification."""
        from shared.escalation.interface import EscalationResponse

        # Submit escalation
        entry = escalation_manager.submit("worker-1", "Need help")

        # Clear previous calls
        mock_dispatcher.dispatch.reset_mock()

        # Create mock escalators
        class MockEscalator:
            def ask(self, issue, context):
                return EscalationResponse(
                    resolved=True,
                    guidance="Here's the solution",
                    escalated_to="manager-1",
                )

            def can_handle(self, issue):
                return True

            def report(self, summary, metadata=None):
                pass

        escalators = {"manager-1": MockEscalator()}

        # Process escalation
        escalation_manager.process(entry.id, escalators)

        # Verify resolved notification was sent
        assert mock_dispatcher.dispatch.called
        notification = mock_dispatcher.dispatch.call_args[0][0]

        assert "Resolved" in notification.title
        assert notification.metadata["event_type"] == "resolved"

    def test_failed_escalation_triggers_failed_notification(
        self, escalation_manager, mock_dispatcher
    ):
        """Test that failed escalation triggers 'failed' notification."""
        from shared.escalation.interface import EscalationResponse

        # Configure to fail after 1 attempt
        escalation_manager._config.retry_attempts = 1

        # Submit escalation
        entry = escalation_manager.submit("worker-1", "Need help")

        # Clear previous calls
        mock_dispatcher.dispatch.reset_mock()

        # Create escalator that doesn't resolve
        class FailingEscalator:
            def ask(self, issue, context):
                return EscalationResponse(resolved=False)

            def can_handle(self, issue):
                return True

            def report(self, summary, metadata=None):
                pass

        escalators = {"manager-1": FailingEscalator()}

        # Process escalation (will fail)
        escalation_manager.process(entry.id, escalators)

        # Verify failed notification was sent
        assert mock_dispatcher.dispatch.called
        notification = mock_dispatcher.dispatch.call_args[0][0]

        assert "Failed" in notification.title
        assert notification.metadata["event_type"] == "failed"

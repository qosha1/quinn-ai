"""
Tests for wrkr communications integration.

Tests the WorkerMessage, Notification, Inbox, Outbox, and NotificationHandler
classes for inter-worker communication.
"""

import pytest
from datetime import datetime, timedelta

from shared.wrkr.comms.types import (
    MessageType,
    Notification,
    TimeSensitivity,
    WorkerMessage,
)
from shared.wrkr.comms.inbox import InMemoryInbox
from shared.wrkr.comms.outbox import InMemoryOutbox
from shared.wrkr.comms.notifications import (
    InMemoryNotificationHandler,
    TaskConversionResult,
    UrgentInterrupt,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def worker_id():
    """Default worker ID for tests."""
    return "worker-1"


@pytest.fixture
def other_worker_id():
    """Another worker ID for message exchange tests."""
    return "worker-2"


@pytest.fixture
def sample_message(worker_id, other_worker_id):
    """Create a sample message for testing."""
    return WorkerMessage(
        id="msg-001",
        sender=other_worker_id,
        recipients=[worker_id],
        subject="Test Subject",
        body="Test message body content.",
        message_type=MessageType.INFORM,
        time_sensitivity=TimeSensitivity.DAYS,
    )


@pytest.fixture
def urgent_message(worker_id, other_worker_id):
    """Create an urgent message for testing."""
    return WorkerMessage(
        id="msg-urgent",
        sender=other_worker_id,
        recipients=[worker_id],
        subject="Urgent Issue",
        body="This requires immediate attention!",
        message_type=MessageType.ESCALATION,
        time_sensitivity=TimeSensitivity.IMMEDIATE,
    )


@pytest.fixture
def inbox(worker_id):
    """Create an in-memory inbox for testing."""
    return InMemoryInbox(worker_id)


@pytest.fixture
def outbox(worker_id):
    """Create an in-memory outbox for testing."""
    return InMemoryOutbox(worker_id)


@pytest.fixture
def notification_handler(worker_id):
    """Create an in-memory notification handler for testing."""
    return InMemoryNotificationHandler(worker_id)


# =============================================================================
# WorkerMessage Tests
# =============================================================================


class TestWorkerMessage:
    """Tests for WorkerMessage dataclass."""

    def test_create_basic_message(self, worker_id, other_worker_id):
        msg = WorkerMessage(
            id="msg-1",
            sender=worker_id,
            recipients=[other_worker_id],
            subject="Hello",
            body="Hi there!",
        )

        assert msg.id == "msg-1"
        assert msg.sender == worker_id
        assert msg.recipients == [other_worker_id]
        assert msg.message_type == MessageType.INFORM
        assert msg.time_sensitivity == TimeSensitivity.WHENEVER

    def test_create_request_message(self, worker_id, other_worker_id):
        msg = WorkerMessage.request(
            id="req-1",
            sender=worker_id,
            recipients=[other_worker_id],
            subject="Question",
            body="What is the status?",
        )

        assert msg.message_type == MessageType.REQUEST
        assert msg.time_sensitivity == TimeSensitivity.DAYS  # Default for requests

    def test_create_response_message(self, worker_id, other_worker_id):
        msg = WorkerMessage.response(
            id="resp-1",
            sender=worker_id,
            recipients=[other_worker_id],
            subject="Re: Question",
            body="The status is good.",
            reply_to="req-1",
            thread_id="thread-1",
        )

        assert msg.message_type == MessageType.RESPONSE
        assert msg.reply_to == "req-1"
        assert msg.thread_id == "thread-1"

    def test_create_escalation_message(self, worker_id, other_worker_id):
        msg = WorkerMessage.escalation(
            id="esc-1",
            sender=worker_id,
            recipients=[other_worker_id],
            subject="Need Help",
            body="I'm stuck on this problem.",
        )

        assert msg.message_type == MessageType.ESCALATION
        assert msg.time_sensitivity == TimeSensitivity.HOURS  # Default for escalations

    def test_create_delegation_message(self, worker_id, other_worker_id):
        msg = WorkerMessage.delegation(
            id="del-1",
            sender=worker_id,
            recipients=[other_worker_id],
            subject="New Task",
            body="Please complete this work.",
            ask_id="ask-123",
            okr_id="okr-456",
        )

        assert msg.message_type == MessageType.DELEGATION
        assert msg.ask_id == "ask-123"
        assert msg.okr_id == "okr-456"

    def test_is_urgent(self, urgent_message, sample_message):
        assert urgent_message.is_urgent()
        assert not sample_message.is_urgent()

    def test_to_dict(self, sample_message):
        d = sample_message.to_dict()

        assert d["id"] == "msg-001"
        assert d["sender"] == "worker-2"
        assert d["recipients"] == ["worker-1"]
        assert d["subject"] == "Test Subject"
        assert d["message_type"] == "inform"
        assert d["time_sensitivity"] == "days"


# =============================================================================
# Notification Tests
# =============================================================================


class TestNotification:
    """Tests for Notification dataclass."""

    def test_create_basic_notification(self, worker_id):
        notif = Notification(
            id="notif-1",
            worker_id=worker_id,
            title="New message",
        )

        assert notif.id == "notif-1"
        assert notif.worker_id == worker_id
        assert notif.time_sensitivity == TimeSensitivity.WHENEVER
        assert notif.source == "system"

    def test_is_urgent(self, worker_id):
        urgent = Notification(
            id="notif-urgent",
            worker_id=worker_id,
            title="Urgent!",
            time_sensitivity=TimeSensitivity.IMMEDIATE,
        )
        normal = Notification(
            id="notif-normal",
            worker_id=worker_id,
            title="Normal",
        )

        assert urgent.is_urgent()
        assert not normal.is_urgent()

    def test_is_expired(self, worker_id):
        expired = Notification(
            id="notif-expired",
            worker_id=worker_id,
            title="Expired",
            expires_at=datetime.now() - timedelta(hours=1),
        )
        active = Notification(
            id="notif-active",
            worker_id=worker_id,
            title="Active",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        no_expiry = Notification(
            id="notif-forever",
            worker_id=worker_id,
            title="Forever",
        )

        assert expired.is_expired()
        assert not active.is_expired()
        assert not no_expiry.is_expired()

    def test_points_to_message(self, worker_id):
        with_message = Notification(
            id="notif-1",
            worker_id=worker_id,
            title="Message notification",
            message_id="msg-001",
        )
        without = Notification(
            id="notif-2",
            worker_id=worker_id,
            title="Generic notification",
        )

        assert with_message.points_to_message()
        assert not without.points_to_message()

    def test_points_to_task(self, worker_id):
        with_task = Notification(
            id="notif-1",
            worker_id=worker_id,
            title="Task notification",
            task_id="task-001",
        )
        without = Notification(
            id="notif-2",
            worker_id=worker_id,
            title="Generic notification",
        )

        assert with_task.points_to_task()
        assert not without.points_to_task()

    def test_from_message(self, sample_message, worker_id):
        notif = Notification.from_message(
            id="notif-from-msg",
            message=sample_message,
            worker_id=worker_id,
        )

        assert notif.message_id == sample_message.id
        assert notif.time_sensitivity == sample_message.time_sensitivity
        assert notif.source == "inbox"
        assert "sender" in notif.metadata


# =============================================================================
# Inbox Tests
# =============================================================================


class TestInMemoryInbox:
    """Tests for InMemoryInbox."""

    def test_add_and_poll_message(self, inbox, sample_message):
        inbox.add_message(sample_message)

        messages = inbox.poll()
        assert len(messages) == 1
        assert messages[0].id == sample_message.id

    def test_poll_filters_read_messages(self, inbox, sample_message):
        inbox.add_message(sample_message)
        inbox.mark_read(sample_message.id)

        messages = inbox.poll()
        assert len(messages) == 0

    def test_get_urgent_filters_non_urgent(self, inbox, sample_message, urgent_message):
        inbox.add_message(sample_message)
        inbox.add_message(urgent_message)

        urgent = inbox.get_urgent()
        assert len(urgent) == 1
        assert urgent[0].id == urgent_message.id

    def test_poll_sorts_by_urgency(self, inbox, worker_id, other_worker_id):
        # Add messages in reverse urgency order
        msg_whenever = WorkerMessage(
            id="msg-1",
            sender=other_worker_id,
            recipients=[worker_id],
            subject="Low",
            body="",
            time_sensitivity=TimeSensitivity.WHENEVER,
        )
        msg_immediate = WorkerMessage(
            id="msg-2",
            sender=other_worker_id,
            recipients=[worker_id],
            subject="High",
            body="",
            time_sensitivity=TimeSensitivity.IMMEDIATE,
        )
        msg_days = WorkerMessage(
            id="msg-3",
            sender=other_worker_id,
            recipients=[worker_id],
            subject="Medium",
            body="",
            time_sensitivity=TimeSensitivity.DAYS,
        )

        inbox.add_message(msg_whenever)
        inbox.add_message(msg_immediate)
        inbox.add_message(msg_days)

        messages = inbox.poll()
        assert messages[0].id == "msg-2"  # IMMEDIATE first
        assert messages[1].id == "msg-3"  # DAYS second
        assert messages[2].id == "msg-1"  # WHENEVER last

    def test_count_unread(self, inbox, sample_message, urgent_message):
        assert inbox.count_unread() == 0

        inbox.add_message(sample_message)
        assert inbox.count_unread() == 1

        inbox.add_message(urgent_message)
        assert inbox.count_unread() == 2

        inbox.mark_read(sample_message.id)
        assert inbox.count_unread() == 1

    def test_get_thread(self, inbox, worker_id, other_worker_id):
        msg1 = WorkerMessage(
            id="msg-1",
            sender=other_worker_id,
            recipients=[worker_id],
            subject="Thread start",
            body="",
            thread_id="thread-1",
        )
        msg2 = WorkerMessage(
            id="msg-2",
            sender=other_worker_id,
            recipients=[worker_id],
            subject="Re: Thread start",
            body="",
            thread_id="thread-1",
            reply_to="msg-1",
        )
        msg3 = WorkerMessage(
            id="msg-3",
            sender=other_worker_id,
            recipients=[worker_id],
            subject="Different thread",
            body="",
            thread_id="thread-2",
        )

        inbox.add_message(msg1)
        inbox.add_message(msg2)
        inbox.add_message(msg3)

        thread = inbox.get_thread("thread-1")
        assert len(thread) == 2
        assert thread[0].id == "msg-1"
        assert thread[1].id == "msg-2"


# =============================================================================
# Outbox Tests
# =============================================================================


class TestInMemoryOutbox:
    """Tests for InMemoryOutbox."""

    def test_send_message(self, outbox, other_worker_id):
        msg = WorkerMessage(
            id="",  # Let outbox generate ID
            sender="",  # Let outbox set sender
            recipients=[other_worker_id],
            subject="Test",
            body="Test body",
        )

        msg_id = outbox.send(msg)

        assert msg_id.startswith("msg-")
        sent = outbox.get_sent()
        assert len(sent) == 1
        assert sent[0].sender == outbox.worker_id

    def test_reply_creates_thread(self, outbox, inbox, worker_id, other_worker_id):
        # Link outbox to inbox for delivery
        other_inbox = InMemoryInbox(other_worker_id)
        outbox.link_inbox(other_inbox)

        # Create original message
        original = WorkerMessage(
            id="original-1",
            sender=other_worker_id,
            recipients=[worker_id],
            subject="Question",
            body="What's the status?",
        )
        inbox.add_message(original)

        # Create a mock outbox that knows about the original
        outbox._sent.append(original)  # Add to sent for reply lookup

        # Reply
        reply_id = outbox.reply(
            original_message_id="original-1",
            body="Status is good!",
        )

        sent = outbox.get_sent()
        reply = next(m for m in sent if m.id == reply_id)

        assert reply.reply_to == "original-1"
        assert reply.thread_id == "original-1"  # Thread ID is original message ID
        assert "Re:" in reply.subject

    def test_broadcast(self, outbox):
        recipients = ["worker-2", "worker-3", "worker-4"]

        msg_ids = outbox.broadcast(
            recipients=recipients,
            subject="Announcement",
            body="This is a broadcast message.",
            time_sensitivity=TimeSensitivity.HOURS,
        )

        assert len(msg_ids) == 1  # One broadcast message
        sent = outbox.get_sent()
        assert sent[0].message_type == MessageType.BROADCAST
        assert sent[0].recipients == recipients

    def test_linked_inbox_receives_message(self, outbox, other_worker_id):
        # Create and link other worker's inbox
        other_inbox = InMemoryInbox(other_worker_id)
        outbox.link_inbox(other_inbox)

        msg = WorkerMessage(
            id="msg-delivery",
            sender=outbox.worker_id,
            recipients=[other_worker_id],
            subject="Delivered",
            body="This should be delivered.",
        )

        outbox.send(msg)

        # Check delivery
        received = other_inbox.poll()
        assert len(received) == 1
        assert received[0].subject == "Delivered"


# =============================================================================
# NotificationHandler Tests
# =============================================================================


class TestInMemoryNotificationHandler:
    """Tests for InMemoryNotificationHandler."""

    def test_poll_returns_pending_notifications(
        self, notification_handler, worker_id
    ):
        notif = Notification(
            id="notif-1",
            worker_id=worker_id,
            title="Test notification",
        )
        notification_handler.add_notification(notif)

        pending = notification_handler.poll()
        assert len(pending) == 1
        assert pending[0].id == "notif-1"

    def test_acknowledged_notifications_not_returned(
        self, notification_handler, worker_id
    ):
        notif = Notification(
            id="notif-1",
            worker_id=worker_id,
            title="Test notification",
        )
        notification_handler.add_notification(notif)
        notification_handler.acknowledge("notif-1")

        pending = notification_handler.poll()
        assert len(pending) == 0

    def test_expired_notifications_not_returned(
        self, notification_handler, worker_id
    ):
        expired_notif = Notification(
            id="notif-expired",
            worker_id=worker_id,
            title="Expired",
            expires_at=datetime.now() - timedelta(hours=1),
        )
        notification_handler.add_notification(expired_notif)

        pending = notification_handler.poll()
        assert len(pending) == 0

    def test_check_urgent_returns_immediate(
        self, notification_handler, worker_id
    ):
        normal = Notification(
            id="notif-normal",
            worker_id=worker_id,
            title="Normal",
            time_sensitivity=TimeSensitivity.DAYS,
        )
        urgent = Notification(
            id="notif-urgent",
            worker_id=worker_id,
            title="Urgent!",
            time_sensitivity=TimeSensitivity.IMMEDIATE,
        )

        notification_handler.add_notification(normal)
        notification_handler.add_notification(urgent)

        result = notification_handler.check_urgent()
        assert result is not None
        assert result.id == "notif-urgent"

    def test_check_urgent_returns_none_when_no_urgent(
        self, notification_handler, worker_id
    ):
        normal = Notification(
            id="notif-normal",
            worker_id=worker_id,
            title="Normal",
            time_sensitivity=TimeSensitivity.DAYS,
        )
        notification_handler.add_notification(normal)

        result = notification_handler.check_urgent()
        assert result is None

    def test_raise_if_urgent(self, notification_handler, worker_id):
        urgent = Notification(
            id="notif-urgent",
            worker_id=worker_id,
            title="Urgent!",
            time_sensitivity=TimeSensitivity.IMMEDIATE,
        )
        notification_handler.add_notification(urgent)

        with pytest.raises(UrgentInterrupt) as exc_info:
            notification_handler.raise_if_urgent()

        assert exc_info.value.notification.id == "notif-urgent"

    def test_convert_message_notification_to_task(
        self, notification_handler, worker_id, sample_message
    ):
        notification_handler.add_message(sample_message)

        notif = Notification.from_message(
            id="notif-1",
            message=sample_message,
            worker_id=worker_id,
        )
        notification_handler.add_notification(notif)

        result = notification_handler.convert_to_task(notif)

        assert result.success
        assert result.task is not None
        assert sample_message.subject in result.task.title
        assert result.task.metadata["message_id"] == sample_message.id

    def test_convert_task_notification(self, notification_handler, worker_id):
        notif = Notification(
            id="notif-task",
            worker_id=worker_id,
            title="New task assigned",
            task_id="task-123",
        )
        notification_handler.add_notification(notif)

        result = notification_handler.convert_to_task(notif)

        assert result.success
        assert result.task.id == "task-123"

    def test_convert_generic_notification(self, notification_handler, worker_id):
        notif = Notification(
            id="notif-generic",
            worker_id=worker_id,
            title="System alert",
            time_sensitivity=TimeSensitivity.HOURS,
            metadata={"description": "Server restart scheduled"},
        )
        notification_handler.add_notification(notif)

        result = notification_handler.convert_to_task(notif)

        assert result.success
        assert result.task.priority == 1  # HOURS -> HIGH priority
        assert "System alert" in result.task.title

    def test_convert_missing_message_fails(self, notification_handler, worker_id):
        notif = Notification(
            id="notif-bad",
            worker_id=worker_id,
            title="Bad notification",
            message_id="nonexistent-msg",
        )
        notification_handler.add_notification(notif)

        result = notification_handler.convert_to_task(notif)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_urgent_callback_invoked(self, worker_id):
        callback_invoked = []

        def on_urgent(notif):
            callback_invoked.append(notif)

        handler = InMemoryNotificationHandler(worker_id, on_urgent=on_urgent)

        urgent = Notification(
            id="notif-urgent",
            worker_id=worker_id,
            title="Urgent!",
            time_sensitivity=TimeSensitivity.IMMEDIATE,
        )
        handler.add_notification(urgent)

        handler.check_urgent()

        assert len(callback_invoked) == 1
        assert callback_invoked[0].id == "notif-urgent"


# =============================================================================
# Integration Tests
# =============================================================================


class TestInboxOutboxIntegration:
    """Tests for inbox/outbox integration."""

    def test_message_flow_between_workers(self, worker_id, other_worker_id):
        # Set up inboxes and outboxes
        inbox_1 = InMemoryInbox(worker_id)
        outbox_1 = InMemoryOutbox(worker_id)

        inbox_2 = InMemoryInbox(other_worker_id)
        outbox_2 = InMemoryOutbox(other_worker_id)

        # Link outboxes to inboxes
        outbox_1.link_inbox(inbox_2)
        outbox_2.link_inbox(inbox_1)

        # Worker 1 sends request to Worker 2
        request = WorkerMessage.request(
            id="req-1",
            sender=worker_id,
            recipients=[other_worker_id],
            subject="Status check",
            body="What's your status?",
        )
        outbox_1.send(request)

        # Worker 2 receives and checks inbox
        received = inbox_2.poll()
        assert len(received) == 1
        assert received[0].subject == "Status check"

        # Worker 2 marks as read and replies
        inbox_2.mark_read("req-1")
        outbox_2._sent.append(received[0])  # Add for reply lookup

        reply_id = outbox_2.reply(
            original_message_id="req-1",
            body="All systems operational!",
        )

        # Worker 1 receives reply
        replies = inbox_1.poll()
        assert len(replies) == 1
        assert replies[0].reply_to == "req-1"
        assert "operational" in replies[0].body


class TestNotificationIntegration:
    """Tests for notification integration with inbox."""

    def test_message_creates_notification_and_task(
        self, worker_id, other_worker_id
    ):
        inbox = InMemoryInbox(worker_id)
        handler = InMemoryNotificationHandler(worker_id)

        # Receive a message
        msg = WorkerMessage.escalation(
            id="esc-1",
            sender=other_worker_id,
            recipients=[worker_id],
            subject="Help needed",
            body="I need help with this problem.",
            time_sensitivity=TimeSensitivity.HOURS,
        )
        inbox.add_message(msg)
        handler.add_message(msg)

        # Create notification from message
        notif = Notification.from_message(
            id="notif-from-esc",
            message=msg,
            worker_id=worker_id,
        )
        handler.add_notification(notif)

        # Convert to task
        result = handler.convert_to_task(notif)

        assert result.success
        assert result.task.priority == 1  # HOURS -> HIGH
        assert msg.subject in result.task.title
        assert result.task.metadata["sender"] == other_worker_id

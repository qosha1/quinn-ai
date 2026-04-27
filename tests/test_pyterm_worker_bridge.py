"""
Tests for WorkerBridge - bridge between pyterm and qn wrkr operations.
"""

import pytest
import json
from unittest.mock import MagicMock, Mock, patch
from datetime import datetime
from pathlib import Path

from cli.core.pyterm.worker_bridge import (
    WorkerBridge,
    WorkItem,
    Notification,
    WorkerStatus,
    SendResult,
    WorkerBridgeError,
    WorkerNotFoundError,
    PermissionDeniedError,
    validate_worker_id,
    SAFE_WORKER_ID_PATTERN,
)


class TestWorkerIdValidation:
    """Tests for worker_id validation."""

    def test_valid_worker_ids(self):
        """Test validation accepts valid worker IDs."""
        valid_ids = [
            "worker-1",
            "ceo",
            "dev_team_lead",
            "Worker123",
            "a-b-c_d_e",
        ]

        for worker_id in valid_ids:
            validate_worker_id(worker_id)  # Should not raise

    def test_empty_worker_id_raises(self):
        """Test empty worker_id raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_worker_id("")

    def test_too_long_worker_id_raises(self):
        """Test worker_id over 128 chars raises ValueError."""
        long_id = "a" * 129

        with pytest.raises(ValueError, match="too long"):
            validate_worker_id(long_id)

    def test_invalid_characters_raise(self):
        """Test worker_id with invalid characters raises."""
        invalid_ids = [
            "worker.1",  # dot not allowed
            "worker/1",  # slash not allowed
            "worker 1",  # space not allowed
            "worker@host",  # @ not allowed
            "worker;cmd",  # semicolon not allowed
            "../etc/passwd",  # path traversal attempt
        ]

        for worker_id in invalid_ids:
            with pytest.raises(ValueError, match="Invalid worker_id format"):
                validate_worker_id(worker_id)

    def test_pattern_match(self):
        """Test SAFE_WORKER_ID_PATTERN regex."""
        assert SAFE_WORKER_ID_PATTERN.match("worker-1")
        assert SAFE_WORKER_ID_PATTERN.match("abc_123")
        assert not SAFE_WORKER_ID_PATTERN.match("worker.1")
        assert not SAFE_WORKER_ID_PATTERN.match("worker/1")


class TestWorkItem:
    """Tests for WorkItem dataclass."""

    def test_creation(self):
        """Test WorkItem creation."""
        item = WorkItem(
            id="bead-1",
            title="Test task",
            priority=2,
            status="open",
            type="task",
        )

        assert item.id == "bead-1"
        assert item.title == "Test task"
        assert item.priority == 2
        assert item.status == "open"
        assert item.type == "task"
        assert item.description == ""
        assert item.metadata == {}

    def test_to_dict(self):
        """Test WorkItem serialization."""
        created = datetime.now()
        item = WorkItem(
            id="bead-1",
            title="Test",
            priority=1,
            status="open",
            type="task",
            description="Desc",
            created_at=created,
            metadata={"key": "value"},
        )

        d = item.to_dict()

        assert d["id"] == "bead-1"
        assert d["title"] == "Test"
        assert d["priority"] == 1
        assert d["created_at"] == created.isoformat()
        assert d["metadata"]["key"] == "value"


class TestNotification:
    """Tests for Notification dataclass."""

    def test_creation(self):
        """Test Notification creation."""
        notif = Notification(
            id="notif-1",
            channel_id="ch-1",
            channel_name="team-chat",
            message_id="msg-1",
            from_worker_id="worker-2",
            content="Hello",
            priority=2,
            status="pending",
        )

        assert notif.id == "notif-1"
        assert notif.channel_name == "team-chat"
        assert notif.content == "Hello"

    def test_to_dict(self):
        """Test Notification serialization."""
        created = datetime.now()
        notif = Notification(
            id="notif-1",
            channel_id="ch-1",
            channel_name="team",
            message_id="msg-1",
            from_worker_id="w2",
            content="Hi",
            priority=1,
            status="pending",
            created_at=created,
        )

        d = notif.to_dict()

        assert d["id"] == "notif-1"
        assert d["content"] == "Hi"
        assert d["created_at"] == created.isoformat()


class TestWorkerStatus:
    """Tests for WorkerStatus dataclass."""

    def test_creation(self):
        """Test WorkerStatus creation."""
        status = WorkerStatus(
            worker_id="w1",
            name="Worker One",
            role="developer",
            lifecycle_status="active",
            runtime_status="working",
            current_task_id="task-1",
            can_work=True,
            is_session_active=True,
        )

        assert status.worker_id == "w1"
        assert status.can_work is True

    def test_to_dict(self):
        """Test WorkerStatus serialization."""
        status = WorkerStatus(
            worker_id="w1",
            name="Worker",
            role="dev",
            lifecycle_status="active",
            runtime_status="idle",
            current_task_id=None,
            can_work=True,
            is_session_active=False,
        )

        d = status.to_dict()

        assert d["worker_id"] == "w1"
        assert d["can_work"] is True
        assert d["current_task_id"] is None


class TestSendResult:
    """Tests for SendResult dataclass."""

    def test_success(self):
        """Test SendResult for successful send."""
        result = SendResult(
            success=True,
            message_id="msg-1",
            channel_name="team",
        )

        assert result.success is True
        assert result.error is None

    def test_failure(self):
        """Test SendResult for failed send."""
        result = SendResult(
            success=False,
            error="Channel not found",
        )

        assert result.success is False
        assert result.message_id is None

    def test_to_dict(self):
        """Test SendResult serialization."""
        result = SendResult(
            success=True,
            message_id="msg-1",
            channel_name="team",
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["message_id"] == "msg-1"


class TestWorkerBridgeInit:
    """Tests for WorkerBridge initialization."""

    @patch('cli.core.pyterm.worker_bridge.Worker')
    def test_init_success(self, mock_worker_class):
        """Test successful initialization."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock(id="worker-1")

        bridge = WorkerBridge(mock_db, "worker-1", org_path="/tmp/org")

        assert bridge.worker_id == "worker-1"
        assert bridge._org_path == "/tmp/org"
        mock_worker_class.get.assert_called_once_with(mock_db, "worker-1")

    @patch('cli.core.pyterm.worker_bridge.Worker')
    def test_init_invalid_worker_id_raises(self, mock_worker_class):
        """Test initialization with invalid worker_id raises."""
        mock_db = Mock()

        with pytest.raises(ValueError, match="Invalid worker_id format"):
            WorkerBridge(mock_db, "worker.invalid", org_path="/tmp")

    @patch('cli.core.pyterm.worker_bridge.Worker')
    def test_init_nonexistent_worker_raises(self, mock_worker_class):
        """Test initialization with nonexistent worker raises."""
        from shared import WorkerNotFound

        mock_db = Mock()
        mock_worker_class.get.side_effect = WorkerNotFound("nonexistent")

        with pytest.raises(WorkerNotFoundError):
            WorkerBridge(mock_db, "nonexistent", org_path="/tmp")

    @patch('cli.core.pyterm.worker_bridge.Worker')
    def test_init_without_org_path(self, mock_worker_class):
        """Test initialization without org_path."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock(id="w1")

        bridge = WorkerBridge(mock_db, "w1")

        assert bridge._org_path is None


class TestWorkerBridgeGetWork:
    """Tests for get_work() method."""

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.run_bd')
    @patch('cli.core.pyterm.worker_bridge.can_worker_access_bead')
    def test_get_work_returns_items(self, mock_can_access, mock_run_bd, mock_worker_class):
        """Test get_work() returns work items."""
        mock_db = Mock()
        mock_worker = Mock(can_work=True)
        mock_worker_class.get.return_value = mock_worker

        # Mock bd list output
        bd_output = json.dumps([
            {
                "id": "bead-1",
                "title": "Task 1",
                "priority": 2,
                "status": "open",
                "type": "task",
                "description": "Desc 1",
            },
            {
                "id": "bead-2",
                "title": "Task 2",
                "priority": 1,
                "status": "in_progress",
                "type": "task",
            },
        ])

        mock_run_bd.return_value = Mock(returncode=0, stdout=bd_output)
        mock_can_access.return_value = True

        bridge = WorkerBridge(mock_db, "worker-1", org_path="/tmp/org")
        items = bridge.get_work(limit=5)

        assert len(items) == 2
        assert items[0].id == "bead-2"  # Priority 1 comes first
        assert items[1].id == "bead-1"  # Priority 2 comes second

    @patch('cli.core.pyterm.worker_bridge.Worker')
    def test_get_work_when_cannot_work(self, mock_worker_class):
        """Test get_work() returns empty when worker can't work."""
        mock_db = Mock()
        mock_worker = Mock(can_work=False)
        mock_worker_class.get.return_value = mock_worker

        bridge = WorkerBridge(mock_db, "worker-1", org_path="/tmp/org")
        items = bridge.get_work()

        assert items == []

    @patch('cli.core.pyterm.worker_bridge.Worker')
    def test_get_work_without_org_path(self, mock_worker_class):
        """Test get_work() returns empty without org_path."""
        mock_db = Mock()
        mock_worker = Mock(can_work=True)
        mock_worker_class.get.return_value = mock_worker

        bridge = WorkerBridge(mock_db, "worker-1")
        items = bridge.get_work()

        assert items == []

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.run_bd')
    def test_get_work_bd_error_returns_empty(self, mock_run_bd, mock_worker_class):
        """Test get_work() returns empty on bd error."""
        mock_db = Mock()
        mock_worker = Mock(can_work=True)
        mock_worker_class.get.return_value = mock_worker

        mock_run_bd.return_value = Mock(returncode=1, stdout="")

        bridge = WorkerBridge(mock_db, "worker-1", org_path="/tmp/org")
        items = bridge.get_work()

        assert items == []

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.run_bd')
    @patch('cli.core.pyterm.worker_bridge.can_worker_access_bead')
    def test_get_work_filters_by_permission(self, mock_can_access, mock_run_bd, mock_worker_class):
        """Test get_work() filters items by permission."""
        mock_db = Mock()
        mock_worker = Mock(can_work=True)
        mock_worker_class.get.return_value = mock_worker

        bd_output = json.dumps([
            {"id": "bead-1", "title": "Task 1", "priority": 1, "status": "open", "type": "task"},
            {"id": "bead-2", "title": "Task 2", "priority": 2, "status": "open", "type": "task"},
        ])

        mock_run_bd.return_value = Mock(returncode=0, stdout=bd_output)

        # Only allow access to bead-1
        mock_can_access.side_effect = lambda db, wid, bid, perm: bid == "bead-1"

        bridge = WorkerBridge(mock_db, "worker-1", org_path="/tmp/org")
        items = bridge.get_work()

        assert len(items) == 1
        assert items[0].id == "bead-1"


class TestWorkerBridgeGetInbox:
    """Tests for get_inbox() method."""

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.get_pending_notifications')
    @patch('cli.core.pyterm.worker_bridge.can_worker_access_channel')
    @patch('cli.core.pyterm.worker_bridge.get_channel')
    @patch('cli.core.pyterm.worker_bridge.get_message')
    def test_get_inbox_returns_notifications(
        self, mock_get_msg, mock_get_ch, mock_can_access, mock_get_notifs, mock_worker_class
    ):
        """Test get_inbox() returns notifications."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        # Mock notification
        mock_notif = Mock(
            id="notif-1",
            channel_id="ch-1",
            message_id="msg-1",
            priority=2,
            status="pending",
            created_at=datetime.now(),
        )
        mock_get_notifs.return_value = [mock_notif]

        # Mock channel with explicit name attribute
        mock_channel = Mock()
        mock_channel.name = "team-chat"
        mock_get_ch.return_value = mock_channel

        # Mock message with explicit attributes
        mock_message = Mock()
        mock_message.from_worker_id = "worker-2"
        mock_message.content = "Hello there"
        mock_get_msg.return_value = mock_message

        mock_can_access.return_value = True

        bridge = WorkerBridge(mock_db, "worker-1")
        notifications = bridge.get_inbox(pending_only=True)

        assert len(notifications) == 1
        assert notifications[0].id == "notif-1"
        assert notifications[0].content == "Hello there"
        assert notifications[0].channel_name == "team-chat"

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.get_pending_notifications')
    @patch('cli.core.pyterm.worker_bridge.can_worker_access_channel')
    def test_get_inbox_filters_by_permission(
        self, mock_can_access, mock_get_notifs, mock_worker_class
    ):
        """Test get_inbox() filters by channel permission."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        mock_notif = Mock(
            id="notif-1",
            channel_id="ch-1",
            message_id="msg-1",
        )
        mock_get_notifs.return_value = [mock_notif]

        # Deny access to channel
        mock_can_access.return_value = False

        bridge = WorkerBridge(mock_db, "worker-1")
        notifications = bridge.get_inbox()

        assert len(notifications) == 0

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.get_worker_notifications')
    def test_get_inbox_pending_only_false(self, mock_get_notifs, mock_worker_class):
        """Test get_inbox() with pending_only=False."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        mock_get_notifs.return_value = []

        bridge = WorkerBridge(mock_db, "worker-1")
        bridge.get_inbox(pending_only=False, limit=100)

        mock_get_notifs.assert_called_once_with(mock_db, "worker-1", limit=100)


class TestWorkerBridgeMarkNotification:
    """Tests for mark_notification_read()."""

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.mark_notification_read')
    def test_mark_notification_read_success(self, mock_mark, mock_worker_class):
        """Test marking notification as read."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        bridge = WorkerBridge(mock_db, "worker-1")
        result = bridge.mark_notification_read("notif-1")

        assert result is True
        mock_mark.assert_called_once_with(mock_db, "notif-1")

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.mark_notification_read')
    def test_mark_notification_read_failure(self, mock_mark, mock_worker_class):
        """Test marking notification handles errors."""
        import sqlite3
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        mock_mark.side_effect = sqlite3.Error("Database error")

        bridge = WorkerBridge(mock_db, "worker-1")
        result = bridge.mark_notification_read("notif-1")

        assert result is False


class TestWorkerBridgeGetPendingCount:
    """Tests for get_pending_count()."""

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.count_pending_notifications')
    def test_get_pending_count(self, mock_count, mock_worker_class):
        """Test get_pending_count() returns count."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        mock_count.return_value = 5

        bridge = WorkerBridge(mock_db, "worker-1")
        count = bridge.get_pending_count()

        assert count == 5
        mock_count.assert_called_once_with(mock_db, "worker-1")


class TestWorkerBridgeSendMessage:
    """Tests for send_message()."""

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.get_channel')
    @patch('cli.core.pyterm.worker_bridge.can_worker_access_channel')
    @patch('cli.core.pyterm.worker_bridge.create_message_with_notifications')
    def test_send_message_success(
        self, mock_create_msg, mock_can_access, mock_get_ch, mock_worker_class
    ):
        """Test successful message send."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        mock_channel = Mock()
        mock_channel.name = "team-chat"
        mock_get_ch.return_value = mock_channel
        mock_can_access.return_value = True

        mock_message = Mock()
        mock_message.id = "msg-1"
        mock_create_msg.return_value = mock_message

        bridge = WorkerBridge(mock_db, "worker-1")
        result = bridge.send_message("ch-1", "Hello team!", priority=2)

        assert result.success is True
        assert result.message_id == "msg-1"
        assert result.channel_name == "team-chat"
        assert result.error is None

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.get_channel')
    def test_send_message_channel_not_found(self, mock_get_ch, mock_worker_class):
        """Test send_message() when channel doesn't exist."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        mock_get_ch.return_value = None

        bridge = WorkerBridge(mock_db, "worker-1")
        result = bridge.send_message("nonexistent", "Hello")

        assert result.success is False
        assert "not found" in result.error

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.get_channel')
    @patch('cli.core.pyterm.worker_bridge.can_worker_access_channel')
    def test_send_message_permission_denied(
        self, mock_can_access, mock_get_ch, mock_worker_class
    ):
        """Test send_message() when permission denied."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        mock_channel = Mock(name="private-channel")
        mock_get_ch.return_value = mock_channel
        mock_can_access.return_value = False

        bridge = WorkerBridge(mock_db, "worker-1")
        result = bridge.send_message("ch-1", "Hello")

        assert result.success is False
        assert "Permission denied" in result.error

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.get_channel')
    @patch('cli.core.pyterm.worker_bridge.can_worker_access_channel')
    def test_send_message_invalid_priority(
        self, mock_can_access, mock_get_ch, mock_worker_class
    ):
        """Test send_message() with invalid priority."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()

        mock_get_ch.return_value = Mock(name="team")
        mock_can_access.return_value = True

        bridge = WorkerBridge(mock_db, "worker-1")
        result = bridge.send_message("ch-1", "Hello", priority=10)

        assert result.success is False
        assert "Invalid priority" in result.error


class TestWorkerBridgeGetStatus:
    """Tests for get_status()."""

    @patch('cli.core.pyterm.worker_bridge.Worker')
    def test_get_status(self, mock_worker_class):
        """Test get_status() returns worker status."""
        mock_db = Mock()
        mock_worker = Mock()
        mock_worker.name = "Worker One"
        mock_worker.role = "developer"
        mock_worker.lifecycle_status = "active"
        mock_worker.runtime_status = "working"
        mock_worker.current_task_id = "task-1"
        mock_worker.can_work = True
        mock_worker.is_session_active = True
        mock_worker_class.get.return_value = mock_worker

        bridge = WorkerBridge(mock_db, "worker-1")
        status = bridge.get_status()

        assert isinstance(status, WorkerStatus)
        assert status.worker_id == "worker-1"
        assert status.name == "Worker One"
        assert status.role == "developer"
        assert status.lifecycle_status == "active"
        assert status.runtime_status == "working"
        assert status.current_task_id == "task-1"
        assert status.can_work is True
        assert status.is_session_active is True


class TestWorkerBridgeSerialization:
    """Tests for to_dict() serialization."""

    @patch('cli.core.pyterm.worker_bridge.Worker')
    @patch('cli.core.pyterm.worker_bridge.count_pending_notifications')
    def test_to_dict(self, mock_count, mock_worker_class):
        """Test to_dict() serialization."""
        mock_db = Mock()
        mock_worker_class.get.return_value = Mock()
        mock_count.return_value = 3

        bridge = WorkerBridge(mock_db, "worker-1", org_path="/tmp/org")
        d = bridge.to_dict()

        assert d["worker_id"] == "worker-1"
        assert d["org_path"] == "/tmp/org"
        assert d["pending_notifications"] == 3


class TestWorkerBridgeErrors:
    """Tests for custom error classes."""

    def test_worker_not_found_error(self):
        """Test WorkerNotFoundError."""
        error = WorkerNotFoundError("worker-1")

        assert error.worker_id == "worker-1"
        assert "Worker not found" in str(error)

    def test_permission_denied_error(self):
        """Test PermissionDeniedError."""
        error = PermissionDeniedError("read", "channel-1")

        assert error.action == "read"
        assert error.resource == "channel-1"
        assert "Permission denied" in str(error)

    def test_worker_bridge_error_base(self):
        """Test WorkerBridgeError is base class."""
        assert issubclass(WorkerNotFoundError, WorkerBridgeError)
        assert issubclass(PermissionDeniedError, WorkerBridgeError)

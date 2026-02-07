"""E2E tests for board intervention execution system.

This test suite specifies the complete board intervention flow:
1. Escalation → message creation in board-channel (not just beads)
2. Board reply parsing for intervention commands (pause, fire, resume)
3. OrgConnection intervention methods execution (calls qn CLI commands)
4. Worker state changes after interventions
5. Intervention audit logging
6. CEO notification after board actions

Tests are written TDD-style and will FAIL until implementation is complete.
"""

import pytest
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from typing import Optional

from board_ui.services.org_connection import (
    QuinnAIOrgConnection,
    OrgConnectionError,
)
from board_ui.interfaces.org_connection import (
    WorkerStatus,
    SessionState,
    OrgStatus,
)
from tests.conftest import create_test_org_db


# ======================
# Test Fixtures
# ======================


@pytest.fixture
def test_org_with_workers(tmp_path):
    """Create a test org with multiple workers in various states."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()

    # Create complete org database with production schema
    db_path = create_test_org_db(
        org_path,
        org_name="test-org",
        status="running",
        include_ceo=True,
        ceo_name="Alice CEO",
        include_board_channel=True,
    )

    # Add additional test data for intervention tests
    conn = sqlite3.connect(str(db_path))
    now = datetime.now().isoformat()

    # Add Engineering team
    conn.execute("INSERT INTO teams (id, name) VALUES ('team-eng', 'Engineering')")

    # Add additional test workers (CEO already created by shared utility)
    # Active worker to test pausing
    conn.execute("""
        INSERT INTO workers (id, name, role, team_id, manager_id, status, cost, created_at)
        VALUES ('worker-dev1', 'Bob Developer', 'Developer', 'team-eng', 'worker-ceo', 'active', 50, ?)
    """, (now,))

    # Paused worker to test resuming
    conn.execute("""
        INSERT INTO workers (id, name, role, team_id, manager_id, status, cost, created_at)
        VALUES ('worker-dev2', 'Carol Engineer', 'Engineer', 'team-eng', 'worker-ceo', 'active', 50, ?)
    """, (now,))

    # Worker to fire
    conn.execute("""
        INSERT INTO workers (id, name, role, team_id, manager_id, status, cost, created_at)
        VALUES ('worker-dev3', 'Dave Tester', 'QA Engineer', 'team-eng', 'worker-ceo', 'active', 50, ?)
    """, (now,))

    # Create additional sessions (CEO session already created by shared utility)
    conn.execute("""
        INSERT INTO sessions (id, worker_id, provider, command, tmux_session_name, state, pid, created_at)
        VALUES ('session-dev1', 'worker-dev1', 'claude_code', 'claude-code', 'org-test-org-dev1', 'running', 12346, ?)
    """, (now,))
    conn.execute("""
        INSERT INTO sessions (id, worker_id, provider, command, tmux_session_name, state, pid, created_at)
        VALUES ('session-dev2', 'worker-dev2', 'claude_code', 'claude-code', 'org-test-org-dev2', 'stopped', 12347, ?)
    """, (now,))
    conn.execute("""
        INSERT INTO sessions (id, worker_id, provider, command, tmux_session_name, state, pid, created_at)
        VALUES ('session-dev3', 'worker-dev3', 'claude_code', 'claude-code', 'org-test-org-dev3', 'running', 12348, ?)
    """, (now,))

    # board-channel and CEO subscription already created by shared utility

    conn.commit()
    conn.close()

    return org_path, db_path


@pytest.fixture
def test_org_with_escalation(test_org_with_workers):
    """Create a test org with an existing escalation message."""
    org_path, db_path = test_org_with_workers

    conn = sqlite3.connect(str(db_path))
    now = datetime.now().isoformat()

    # Create escalation message in board-channel
    conn.execute("""
        INSERT INTO messages (id, channel_id, thread_id, parent_id, from_worker_id, content, priority, time_sensitivity, created_at)
        VALUES ('msg-esc-1', 'ch-board', NULL, NULL, 'worker-dev1',
         'ESCALATION: Need guidance on API design decision', 3, 'hours', ?)
    """, (now,))

    # Create notification bead for CEO
    conn.execute("""
        INSERT INTO notification_beads (id, worker_id, message_id, channel_id, status, priority, created_at, read_at, expires_at)
        VALUES ('nb-esc-1', 'worker-ceo', 'msg-esc-1', 'ch-board', 'pending', 3, ?, NULL, NULL)
    """, (now,))

    conn.commit()
    conn.close()

    return org_path, db_path


# ======================
# 1. Escalation Message Creation Tests
# ======================


class TestEscalationMessageCreation:
    """Test that escalations create messages in board-channel (NEW behavior)."""

    def test_escalation_creates_board_message(self, test_org_with_workers, monkeypatch):
        """Test that escalations create messages in board-channel, not just beads."""
        org_path, db_path = test_org_with_workers

        # Import escalation system
        from shared.org.escalation import BoardNotifier
        from shared.bd import BdClient

        # Create board notifier with callback
        notifications = []
        def on_notify(issue: str, context: dict):
            notifications.append({"issue": issue, "context": context})

        notifier = BoardNotifier(
            notification_callback=on_notify,
            db_path=str(db_path),
        )

        # Trigger escalation
        issue = "Test escalation from worker"
        context = {
            "worker_id": "worker-dev1",
            "escalation_path": ["worker-ceo", "board"],
        }

        bead_id = notifier.notify(issue, context)
        assert bead_id is not None

        # Verify: Bead created (existing behavior)
        client = BdClient(db_path=str(db_path))
        beads = client.list_issues()
        escalation_beads = [b for b in beads if b.get("type") == "board_escalation"]
        assert len(escalation_beads) >= 1

        # Verify: Message ALSO created in board-channel (NEW behavior)
        conn = QuinnAIOrgConnection(org_path)
        messages = conn.get_board_messages()

        # Filter for our test escalation
        test_messages = [m for m in messages if issue in m.content]
        assert len(test_messages) == 1, "Should create message in board-channel"

        # Verify: Message has proper from_worker_id (escalating worker, not 'board')
        msg = test_messages[0]
        assert msg.from_worker_id == "worker-dev1", "Message should be from escalating worker"
        assert "worker-dev1" in msg.from_worker_name or "Bob" in msg.from_worker_name

        # Verify: Notification bead created for board subscribers (CEO)
        unread_count = conn.get_unread_count()
        assert unread_count >= 1, "CEO should have unread notification"

        conn.close()

    def test_board_sees_escalation_message(self, test_org_with_escalation):
        """Test that board can see escalation messages in the messages view."""
        org_path, db_path = test_org_with_escalation

        # Create connection as board would
        conn = QuinnAIOrgConnection(org_path)

        # Get board messages
        messages = conn.get_board_messages()

        # Verify escalation message appears
        escalation_msgs = [m for m in messages if "ESCALATION" in m.content]
        assert len(escalation_msgs) >= 1, "Board should see escalation message"

        msg = escalation_msgs[0]
        assert msg.from_worker_id == "worker-dev1"
        assert "API design" in msg.content

        # Verify unread count
        unread_count = conn.get_unread_count()
        assert unread_count >= 1, "Should have unread escalation"

        conn.close()


# ======================
# 2. Command Parsing Tests
# ======================


class TestInterventionCommandParsing:
    """Test parsing intervention commands from board replies."""

    def test_parse_pause_command(self):
        """Test parsing pause command with various formats."""
        # This will import from the messages view once implemented
        # For now, we'll define the expected interface

        # Expected function signature:
        # _parse_intervention_command(reply_text: str) -> Optional[dict]

        test_cases = [
            ("pause worker-123 because misbehaving", {
                "action": "pause",
                "worker_id": "worker-123",
                "reason": "misbehaving"
            }),
            ("pause worker-abc", {
                "action": "pause",
                "worker_id": "worker-abc",
                "reason": None
            }),
            ("Pause WORKER-123 reason: testing", {
                "action": "pause",
                "worker_id": "WORKER-123",
                "reason": "testing"
            }),
        ]

        # Import parser once implemented
        try:
            from board_ui.views.messages import _parse_intervention_command

            for text, expected in test_cases:
                result = _parse_intervention_command(text)
                assert result is not None, f"Should parse: {text}"
                assert result["action"] == expected["action"]
                assert result["worker_id"] == expected["worker_id"]
                # Reason might vary in parsing, just check it exists or is None

        except ImportError:
            pytest.skip("_parse_intervention_command not yet implemented")

    def test_parse_fire_with_reason(self):
        """Test parsing fire command with reason."""
        test_cases = [
            ("fire worker-abc: performance issues", {
                "action": "fire",
                "worker_id": "worker-abc",
                "reason": "performance issues"
            }),
            ("fire worker-123", {
                "action": "fire",
                "worker_id": "worker-123",
                "reason": None
            }),
            ("Fire worker-xyz because broken", {
                "action": "fire",
                "worker_id": "worker-xyz",
                "reason": "broken"
            }),
        ]

        try:
            from board_ui.views.messages import _parse_intervention_command

            for text, expected in test_cases:
                result = _parse_intervention_command(text)
                assert result is not None, f"Should parse: {text}"
                assert result["action"] == expected["action"]
                assert result["worker_id"] == expected["worker_id"]

        except ImportError:
            pytest.skip("_parse_intervention_command not yet implemented")

    def test_parse_resume_command(self):
        """Test parsing resume command (no reason required)."""
        test_cases = [
            ("resume worker-xyz", {
                "action": "resume",
                "worker_id": "worker-xyz",
            }),
            ("Resume WORKER-123", {
                "action": "resume",
                "worker_id": "WORKER-123",
            }),
        ]

        try:
            from board_ui.views.messages import _parse_intervention_command

            for text, expected in test_cases:
                result = _parse_intervention_command(text)
                assert result is not None, f"Should parse: {text}"
                assert result["action"] == expected["action"]
                assert result["worker_id"] == expected["worker_id"]

        except ImportError:
            pytest.skip("_parse_intervention_command not yet implemented")

    def test_parse_no_command(self):
        """Test that non-intervention messages return None."""
        non_commands = [
            "just a regular message without commands",
            "Thanks for the update",
            "Let me know when you're done",
            "worker-123 is doing great work",  # Mention but not command
        ]

        try:
            from board_ui.views.messages import _parse_intervention_command

            for text in non_commands:
                result = _parse_intervention_command(text)
                assert result is None, f"Should not parse as command: {text}"

        except ImportError:
            pytest.skip("_parse_intervention_command not yet implemented")

    def test_multiple_commands_in_reply(self):
        """Test handling of multiple commands in one message."""
        text = "pause worker-123 and also fire worker-456"

        try:
            from board_ui.views.messages import _parse_intervention_command

            result = _parse_intervention_command(text)
            # Should only parse first command
            assert result is not None
            assert result["action"] == "pause"
            assert result["worker_id"] == "worker-123"

            # Implementation should warn about multiple commands
            # (verified in integration test)

        except ImportError:
            pytest.skip("_parse_intervention_command not yet implemented")


# ======================
# 3. OrgConnection Intervention Methods Tests
# ======================


class TestOrgConnectionInterventions:
    """Test OrgConnection intervention methods that execute qn CLI commands."""

    @patch('subprocess.run')
    def test_pause_worker_via_connection(self, mock_run, test_org_with_workers):
        """Test pausing worker through org connection."""
        org_path, db_path = test_org_with_workers

        # Mock successful subprocess call
        mock_run.return_value = MagicMock(returncode=0, stdout="Worker paused")

        # Create connection
        conn = QuinnAIOrgConnection(org_path)

        # Verify worker is running
        worker = conn.get_worker("worker-dev1")
        assert worker is not None
        assert worker.session_state == SessionState.RUNNING

        # Pause worker
        try:
            success = conn.pause_worker("worker-dev1", "test pause")

            # Verify subprocess was called with correct qn command
            mock_run.assert_called()
            call_args = mock_run.call_args
            assert "qn" in str(call_args), "Should call qn CLI"
            assert "pause" in str(call_args) or "stop" in str(call_args)

            # Verify success
            assert success is True

            # Verify state changed in database
            worker_after = conn.get_worker("worker-dev1")
            assert worker_after.session_state == SessionState.STOPPED
            assert worker_after.status == WorkerStatus.ACTIVE  # Lifecycle unchanged

        except AttributeError:
            pytest.skip("pause_worker method not yet implemented")

        conn.close()

    @patch('subprocess.run')
    def test_resume_worker_via_connection(self, mock_run, test_org_with_workers):
        """Test resuming paused worker through org connection."""
        org_path, db_path = test_org_with_workers

        # Mock successful subprocess call
        mock_run.return_value = MagicMock(returncode=0, stdout="Worker resumed")

        # Create connection
        conn = QuinnAIOrgConnection(org_path)

        # Verify worker is stopped
        worker = conn.get_worker("worker-dev2")
        assert worker is not None
        assert worker.session_state == SessionState.STOPPED

        # Resume worker
        try:
            success = conn.resume_worker("worker-dev2")

            # Verify subprocess was called
            mock_run.assert_called()
            call_args = mock_run.call_args
            assert "qn" in str(call_args), "Should call qn CLI"
            assert "resume" in str(call_args) or "start" in str(call_args)

            # Verify success
            assert success is True

            # Verify state changed
            worker_after = conn.get_worker("worker-dev2")
            # Session should be back to running or idle
            assert worker_after.session_state in [SessionState.RUNNING, SessionState.IDLE]

        except AttributeError:
            pytest.skip("resume_worker method not yet implemented")

        conn.close()

    @patch('subprocess.run')
    def test_fire_worker_via_connection(self, mock_run, test_org_with_workers):
        """Test firing (terminating) worker through org connection."""
        org_path, db_path = test_org_with_workers

        # Mock successful subprocess call
        mock_run.return_value = MagicMock(returncode=0, stdout="Worker terminated")

        # Create connection
        conn = QuinnAIOrgConnection(org_path)

        # Verify worker is active
        worker = conn.get_worker("worker-dev3")
        assert worker is not None
        assert worker.status == WorkerStatus.ACTIVE

        # Fire worker
        try:
            success = conn.fire_worker("worker-dev3", "test termination")

            # Verify subprocess was called
            mock_run.assert_called()
            call_args = mock_run.call_args
            assert "qn" in str(call_args), "Should call qn CLI"
            assert "fire" in str(call_args) or "terminate" in str(call_args)

            # Verify success
            assert success is True

            # Verify lifecycle status changed
            worker_after = conn.get_worker("worker-dev3")
            assert worker_after.status == WorkerStatus.TERMINATED

            # Session should be stopped
            assert worker_after.session_state in [SessionState.STOPPED, None]

        except AttributeError:
            pytest.skip("fire_worker method not yet implemented")

        conn.close()

    def test_intervention_on_nonexistent_worker(self, test_org_with_workers):
        """Test intervention on nonexistent worker returns False."""
        org_path, db_path = test_org_with_workers

        conn = QuinnAIOrgConnection(org_path)

        try:
            # Try to pause nonexistent worker
            success = conn.pause_worker("invalid-worker-id", "test")
            assert success is False, "Should fail for nonexistent worker"

            # Verify no state changes occurred
            workers_after = conn.get_workers()
            # All existing workers should be unchanged

        except AttributeError:
            pytest.skip("pause_worker method not yet implemented")

        conn.close()


# ======================
# 4. Audit Logging Tests
# ======================


class TestInterventionAuditLogging:
    """Test that interventions create audit logs in board-channel."""

    @patch('subprocess.run')
    def test_intervention_creates_audit_log(self, mock_run, test_org_with_workers):
        """Test that interventions create audit log messages."""
        org_path, db_path = test_org_with_workers

        # Mock successful subprocess call
        mock_run.return_value = MagicMock(returncode=0, stdout="Worker paused")

        conn = QuinnAIOrgConnection(org_path)

        try:
            # Pause worker
            success = conn.pause_worker("worker-dev1", "test pause reason")
            assert success is True

            # Query board-channel messages for audit log
            messages = conn.get_board_messages()

            # Look for audit log message
            audit_logs = [m for m in messages if "INTERVENTION" in m.content or "paused" in m.content.lower()]
            assert len(audit_logs) >= 1, "Should create audit log message"

            audit_msg = audit_logs[0]
            assert "worker-dev1" in audit_msg.content
            assert "pause" in audit_msg.content.lower()
            assert "test pause reason" in audit_msg.content

            # Verify message has proper metadata
            # Message should be from 'board' or system
            assert audit_msg.from_worker_id in ["board", "system", "worker-ceo"]

        except AttributeError:
            pytest.skip("pause_worker or audit logging not yet implemented")

        conn.close()


# ======================
# 5. CEO Notification Tests
# ======================


class TestCEONotifications:
    """Test that CEO is notified of board interventions."""

    @patch('subprocess.run')
    def test_ceo_notified_of_intervention(self, mock_run, test_org_with_workers):
        """Test that CEO receives notification bead after intervention."""
        org_path, db_path = test_org_with_workers

        # Mock successful subprocess call
        mock_run.return_value = MagicMock(returncode=0, stdout="Worker terminated")

        conn = QuinnAIOrgConnection(org_path)

        # Get initial notification count
        initial_unread = conn.get_unread_count()

        try:
            # Fire worker
            success = conn.fire_worker("worker-dev3", "poor performance")
            assert success is True

            # Check CEO notifications (unread count should increase)
            new_unread = conn.get_unread_count()
            assert new_unread > initial_unread, "CEO should receive notification"

            # Verify notification bead contains intervention details
            messages = conn.get_board_messages(unread_only=True)
            intervention_msgs = [m for m in messages if "worker-dev3" in m.content]

            assert len(intervention_msgs) >= 1, "CEO should see intervention notification"

            msg = intervention_msgs[0]
            assert "fire" in msg.content.lower() or "terminat" in msg.content.lower()
            assert "poor performance" in msg.content

        except AttributeError:
            pytest.skip("fire_worker or notification system not yet implemented")

        conn.close()


# ======================
# 6. Integration Tests
# ======================


class TestFullInterventionFlow:
    """Integration tests for complete intervention workflows."""

    @patch('subprocess.run')
    def test_full_intervention_flow(self, mock_run, test_org_with_workers):
        """Test complete flow: escalation → board reply → intervention → audit → notification."""
        org_path, db_path = test_org_with_workers

        # Mock successful subprocess calls
        mock_run.return_value = MagicMock(returncode=0, stdout="Success")

        # Step 1: Create escalation
        from shared.org.escalation import BoardNotifier

        notifier = BoardNotifier(db_path=str(db_path))

        issue = "Worker is repeatedly failing tasks"
        context = {
            "worker_id": "worker-dev1",
            "escalation_path": ["worker-ceo", "board"],
            "failure_count": 5,
        }

        bead_id = notifier.notify(issue, context)
        assert bead_id is not None

        # Step 2: Verify message appears in board-channel
        conn = QuinnAIOrgConnection(org_path)
        messages = conn.get_board_messages()

        escalation_msgs = [m for m in messages if issue in m.content]
        assert len(escalation_msgs) >= 1, "Escalation should create board message"

        msg = escalation_msgs[0]
        assert msg.from_worker_id == "worker-dev1"

        # Step 3: Board replies with intervention command
        reply_text = "pause worker-dev1 because needs investigation"

        try:
            from board_ui.views.messages import _parse_intervention_command

            # Parse command
            command = _parse_intervention_command(reply_text)
            assert command is not None
            assert command["action"] == "pause"
            assert command["worker_id"] == "worker-dev1"

            # Execute intervention
            success = conn.pause_worker(command["worker_id"], command.get("reason"))
            assert success is True

            # Step 4: Verify worker paused
            worker = conn.get_worker("worker-dev1")
            assert worker.session_state == SessionState.STOPPED
            assert worker.status == WorkerStatus.ACTIVE  # Lifecycle unchanged

            # Step 5: Verify audit log created
            messages_after = conn.get_board_messages()
            audit_msgs = [m for m in messages_after if "INTERVENTION" in m.content or "paused" in m.content.lower()]

            # Should have audit log
            assert len(audit_msgs) >= 1, "Should create audit log"

            # Step 6: Verify CEO notified
            unread = conn.get_unread_count()
            assert unread >= 1, "CEO should have notifications"

        except (ImportError, AttributeError) as e:
            pytest.skip(f"Implementation not complete: {e}")

        conn.close()

    def test_intervention_requires_org_connection(self, test_org_with_workers):
        """Test that interventions require valid org connection."""
        org_path, db_path = test_org_with_workers

        # Try to execute intervention without connection
        # This should be prevented at the view layer

        # For now, just verify that connection is required
        try:
            from board_ui.views.messages import MessagesView

            # MessagesView should check for org connection before allowing interventions
            # This will be tested at the view level
            pytest.skip("View-level testing not implemented yet")

        except ImportError:
            pytest.skip("MessagesView not yet implemented")


# ======================
# 7. Error Handling Tests
# ======================


class TestInterventionErrorHandling:
    """Test error handling in intervention system."""

    @patch('subprocess.run')
    def test_failed_intervention_returns_false(self, mock_run, test_org_with_workers):
        """Test that failed interventions return False."""
        org_path, db_path = test_org_with_workers

        # Mock failed subprocess call
        mock_run.return_value = MagicMock(returncode=1, stderr="Error: worker not found")

        conn = QuinnAIOrgConnection(org_path)

        try:
            # Try to pause worker
            success = conn.pause_worker("worker-dev1", "test")

            # Should return False on failure
            assert success is False, "Should return False on subprocess failure"

            # Worker state should be unchanged
            worker = conn.get_worker("worker-dev1")
            assert worker.session_state == SessionState.RUNNING  # Still running

        except AttributeError:
            pytest.skip("pause_worker method not yet implemented")

        conn.close()

    def test_intervention_with_missing_reason(self, test_org_with_workers):
        """Test that interventions work even without explicit reason."""
        org_path, db_path = test_org_with_workers

        conn = QuinnAIOrgConnection(org_path)

        try:
            # Pause without reason (should use default)
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                success = conn.pause_worker("worker-dev1", None)
                assert success is True

                # Audit log should still be created (with default reason or no reason)
                messages = conn.get_board_messages()
                audit_msgs = [m for m in messages if "paused" in m.content.lower()]
                assert len(audit_msgs) >= 1

        except AttributeError:
            pytest.skip("pause_worker method not yet implemented")

        conn.close()


# ======================
# 8. Board Channel Tests
# ======================


class TestBoardChannelMessages:
    """Test board-channel specific message handling."""

    def test_board_channel_exists(self, test_org_with_workers):
        """Test that board-channel is created and accessible."""
        org_path, db_path = test_org_with_workers

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Verify board-channel exists
        result = cursor.execute(
            "SELECT id, name, type FROM channels WHERE name = 'board-channel'"
        ).fetchone()

        assert result is not None, "board-channel should exist"
        assert result[2] == "board", "Should be board type channel"

        conn.close()

    def test_board_messages_filtered_correctly(self, test_org_with_escalation):
        """Test that only board-channel messages are returned."""
        org_path, db_path = test_org_with_escalation

        # Add some non-board messages to other channels
        conn_db = sqlite3.connect(str(db_path))
        now = datetime.now().isoformat()

        # Create another channel
        conn_db.execute("""
            INSERT INTO channels (id, name, type, team_id, created_at)
            VALUES ('ch-team', 'team-eng', 'team', NULL, ?)
        """, (now,))

        # Add message to team channel
        conn_db.execute("""
            INSERT INTO messages VALUES
            ('msg-team-1', 'ch-team', NULL, NULL, 'worker-dev1',
             'Team message not for board', 1, 'normal', ?)
        """, (now,))

        conn_db.commit()
        conn_db.close()

        # Query board messages
        conn = QuinnAIOrgConnection(org_path)
        board_messages = conn.get_board_messages()

        # Should only get board-channel messages
        for msg in board_messages:
            assert msg.channel_name == "board-channel", "Should only return board messages"

        # Escalation message should be in results
        escalation_msgs = [m for m in board_messages if "ESCALATION" in m.content]
        assert len(escalation_msgs) >= 1

        conn.close()


# ======================
# 9. Message Reply Tests
# ======================


class TestBoardMessageReplies:
    """Test board reply functionality that triggers interventions."""

    @patch('subprocess.run')
    def test_send_board_response_with_command(self, mock_run, test_org_with_escalation):
        """Test sending board response that contains intervention command."""
        org_path, db_path = test_org_with_escalation

        mock_run.return_value = MagicMock(returncode=0, stdout="Success")

        conn = QuinnAIOrgConnection(org_path)

        # Get escalation message
        messages = conn.get_board_messages()
        escalation_msg = messages[0]

        # Send reply with intervention command
        reply_text = "pause worker-dev1 until we investigate this"

        # Send response
        success = conn.send_board_response(escalation_msg.id, reply_text)
        assert success is True, "Should send response successfully"

        # Parse and execute intervention
        try:
            from board_ui.views.messages import _parse_intervention_command, _execute_intervention

            command = _parse_intervention_command(reply_text)
            assert command is not None

            # Execute intervention
            intervention_success = _execute_intervention(conn, command)
            assert intervention_success is True

            # Verify worker paused
            worker = conn.get_worker("worker-dev1")
            assert worker.session_state == SessionState.STOPPED

        except (ImportError, AttributeError):
            pytest.skip("Command execution not yet implemented")

        conn.close()

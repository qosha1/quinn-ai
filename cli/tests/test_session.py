"""
Unit tests for Session abstraction layer.

Tests the SessionInterface ABC, SessionState enum, SessionConfig,
and state machine validation.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

from cli.core.session import (
    SessionState,
    SessionId,
    SessionConfig,
    SessionMetrics,
    SessionOutput,
    PromptResult,
    SessionInterface,
    SessionError,
    SessionSpawnError,
    SessionAlreadyRunningError,
    SessionNotRunningError,
    SessionNotReadyError,
    SessionTimeoutError,
    SessionAlreadyBoundError,
    InvalidSessionStateTransition,
    SESSION_STATE_TRANSITIONS,
)


# =========================================================================
# Mock Session Implementation for Testing
# =========================================================================

class MockSession(SessionInterface):
    """Mock session implementation for testing the abstract interface."""

    def __init__(self, config: SessionConfig):
        super().__init__(config)
        self._mock_pid: Optional[int] = None
        self._mock_responses: list[str] = []
        self._response_index = 0
        self._spawn_called = False
        self._terminate_called = False
        self._force_terminate = False
        self._inputs_sent: list[str] = []
        self._should_fail_spawn = False
        self._ready_after_reads = 1  # How many reads before ready
        self._complete_after_reads = 1  # How many reads before complete
        self._read_count = 0

    def set_responses(self, responses: list[str]) -> None:
        """Set mock responses to return."""
        self._mock_responses = responses
        self._response_index = 0

    def set_should_fail_spawn(self, should_fail: bool) -> None:
        """Set whether spawn should fail."""
        self._should_fail_spawn = should_fail

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def pid(self) -> Optional[int]:
        return self._mock_pid

    def _spawn_process(self) -> None:
        if self._should_fail_spawn:
            raise SessionSpawnError(self._id, "Mock spawn failure")
        self._spawn_called = True
        self._mock_pid = 12345

    def _terminate_process(self, force: bool = False) -> None:
        self._terminate_called = True
        self._force_terminate = force
        self._mock_pid = None

    def _send_input(self, text: str) -> None:
        self._inputs_sent.append(text)

    def _read_output(self, timeout_ms: Optional[int] = None) -> SessionOutput:
        self._read_count += 1
        if self._response_index < len(self._mock_responses):
            content = self._mock_responses[self._response_index]
            self._response_index += 1
        else:
            content = ""
        return SessionOutput(content=content, timestamp=datetime.now())

    def _detect_ready(self, output: str) -> bool:
        return self._read_count >= self._ready_after_reads

    def _detect_completion(self, output: str) -> bool:
        return self._read_count >= self._complete_after_reads

    def _get_context_usage(self) -> int:
        return 1000

    def _send_interrupt(self) -> None:
        pass


# =========================================================================
# Test Fixtures
# =========================================================================

@pytest.fixture
def config():
    """Create basic session config."""
    return SessionConfig(
        worker_id="worker-123",
        provider="mock",
        command="/usr/bin/mock-cli",
        args=["--test"],
    )


@pytest.fixture
def session(config):
    """Create mock session instance."""
    return MockSession(config)


# =========================================================================
# SessionState Tests
# =========================================================================

class TestSessionState:
    """Test SessionState enum."""

    def test_all_states_defined(self):
        """All expected states should be defined."""
        assert SessionState.STARTING.value == "starting"
        assert SessionState.RUNNING.value == "running"
        assert SessionState.IDLE.value == "idle"
        assert SessionState.STOPPED.value == "stopped"
        assert SessionState.CRASHED.value == "crashed"

    def test_state_count(self):
        """Should have exactly 5 states."""
        assert len(SessionState) == 5


class TestSessionStateTransitions:
    """Test state transition map."""

    def test_all_states_have_transitions(self):
        """All states should have defined transitions."""
        for state in SessionState:
            assert state in SESSION_STATE_TRANSITIONS

    def test_starting_transitions(self):
        """STARTING can go to RUNNING or CRASHED."""
        valid = SESSION_STATE_TRANSITIONS[SessionState.STARTING]
        assert SessionState.RUNNING in valid
        assert SessionState.CRASHED in valid
        assert len(valid) == 2

    def test_running_transitions(self):
        """RUNNING can go to IDLE or CRASHED."""
        valid = SESSION_STATE_TRANSITIONS[SessionState.RUNNING]
        assert SessionState.IDLE in valid
        assert SessionState.CRASHED in valid
        assert len(valid) == 2

    def test_idle_transitions(self):
        """IDLE can go to RUNNING, STOPPED, or CRASHED."""
        valid = SESSION_STATE_TRANSITIONS[SessionState.IDLE]
        assert SessionState.RUNNING in valid
        assert SessionState.STOPPED in valid
        assert SessionState.CRASHED in valid
        assert len(valid) == 3

    def test_stopped_transitions(self):
        """STOPPED can go to STARTING (restart)."""
        valid = SESSION_STATE_TRANSITIONS[SessionState.STOPPED]
        assert SessionState.STARTING in valid
        assert len(valid) == 1

    def test_crashed_transitions(self):
        """CRASHED can go to STARTING (restart) or STOPPED (cleanup)."""
        valid = SESSION_STATE_TRANSITIONS[SessionState.CRASHED]
        assert SessionState.STARTING in valid
        assert SessionState.STOPPED in valid
        assert len(valid) == 2


# =========================================================================
# SessionId Tests
# =========================================================================

class TestSessionId:
    """Test SessionId dataclass."""

    def test_create_session_id(self):
        """Should create session ID with worker and instance."""
        session_id = SessionId.create("worker-123")
        assert session_id.worker_id == "worker-123"
        assert len(session_id.instance_id) == 12

    def test_str_format(self):
        """String format should be worker_id:instance_id."""
        session_id = SessionId(worker_id="worker-123", instance_id="abc123def456")
        assert str(session_id) == "worker-123:abc123def456"

    def test_unique_instance_ids(self):
        """Each creation should produce unique instance ID."""
        id1 = SessionId.create("worker-123")
        id2 = SessionId.create("worker-123")
        assert id1.instance_id != id2.instance_id

    def test_hashable(self):
        """SessionId should be hashable for use in dicts/sets."""
        id1 = SessionId(worker_id="w1", instance_id="i1")
        id2 = SessionId(worker_id="w1", instance_id="i1")
        assert hash(id1) == hash(id2)
        assert id1 == id2

    def test_immutable(self):
        """SessionId should be immutable (frozen)."""
        session_id = SessionId.create("worker-123")
        with pytest.raises(AttributeError):
            session_id.worker_id = "different"


# =========================================================================
# SessionConfig Tests
# =========================================================================

class TestSessionConfig:
    """Test SessionConfig dataclass."""

    def test_required_fields(self):
        """Should require worker_id, provider, and command."""
        config = SessionConfig(
            worker_id="worker-123",
            provider="claude_code",
            command="/usr/bin/claude",
        )
        assert config.worker_id == "worker-123"
        assert config.provider == "claude_code"
        assert config.command == "/usr/bin/claude"

    def test_default_values(self):
        """Should have sensible defaults."""
        config = SessionConfig(
            worker_id="worker-123",
            provider="test",
            command="/bin/test",
        )
        assert config.args == []
        assert config.working_directory is None
        assert config.env_vars == {}
        assert config.cols == 120
        assert config.rows == 40
        assert config.startup_timeout_ms == 30000
        assert config.idle_timeout_ms == 300000
        assert config.response_timeout_ms == 600000
        assert config.max_context_tokens == 100000
        assert config.memory_limit_mb is None
        assert config.persist_transcript is True
        assert config.transcript_db_path is None

    def test_custom_values(self):
        """Should accept custom values."""
        config = SessionConfig(
            worker_id="worker-123",
            provider="test",
            command="/bin/test",
            args=["--flag", "value"],
            working_directory=Path("/tmp/work"),
            env_vars={"KEY": "VALUE"},
            cols=200,
            rows=50,
            startup_timeout_ms=60000,
            max_context_tokens=200000,
        )
        assert config.args == ["--flag", "value"]
        assert config.working_directory == Path("/tmp/work")
        assert config.env_vars == {"KEY": "VALUE"}
        assert config.cols == 200
        assert config.rows == 50
        assert config.startup_timeout_ms == 60000
        assert config.max_context_tokens == 200000


# =========================================================================
# SessionMetrics Tests
# =========================================================================

class TestSessionMetrics:
    """Test SessionMetrics dataclass."""

    def test_initial_metrics(self):
        """Should initialize with created_at and zeros."""
        now = datetime.now()
        metrics = SessionMetrics(created_at=now)
        assert metrics.created_at == now
        assert metrics.started_at is None
        assert metrics.stopped_at is None
        assert metrics.prompts_sent == 0
        assert metrics.responses_received == 0
        assert metrics.errors_count == 0

    def test_mutable(self):
        """Metrics should be mutable for updates."""
        metrics = SessionMetrics(created_at=datetime.now())
        metrics.prompts_sent = 5
        metrics.errors_count = 2
        assert metrics.prompts_sent == 5
        assert metrics.errors_count == 2


# =========================================================================
# SessionInterface Tests
# =========================================================================

class TestSessionInterfaceCreation:
    """Test SessionInterface initialization."""

    def test_initial_state(self, session):
        """New session should be in STOPPED state."""
        assert session.state == SessionState.STOPPED

    def test_session_id_created(self, session, config):
        """Session should have unique ID based on worker."""
        assert session.id.worker_id == config.worker_id
        assert len(session.id.instance_id) == 12

    def test_config_accessible(self, session, config):
        """Config should be accessible."""
        assert session.config == config

    def test_metrics_initialized(self, session):
        """Metrics should be initialized."""
        assert session.metrics.created_at is not None
        assert session.metrics.prompts_sent == 0

    def test_not_bound_initially(self, session):
        """Session should not be bound to worker initially."""
        assert session.bound_worker_id is None

    def test_is_alive_initially_false(self, session):
        """Session should not be alive when stopped."""
        assert session.is_alive is False

    def test_is_ready_initially_false(self, session):
        """Session should not be ready when stopped."""
        assert session.is_ready is False


class TestSessionLifecycle:
    """Test session lifecycle methods."""

    def test_start_transitions_to_idle(self, session):
        """Start should transition through STARTING -> RUNNING -> IDLE."""
        session.start()
        assert session.state == SessionState.IDLE
        assert session._spawn_called is True

    def test_start_sets_pid(self, session):
        """Start should result in a PID."""
        session.start()
        assert session.pid == 12345

    def test_start_updates_metrics(self, session):
        """Start should update started_at metric."""
        session.start()
        assert session.metrics.started_at is not None

    def test_start_when_running_raises(self, session):
        """Starting an already running session should raise."""
        session.start()
        with pytest.raises(SessionAlreadyRunningError):
            session.start()

    def test_start_when_idle_raises(self, session):
        """Starting an idle session should raise."""
        session.start()
        assert session.state == SessionState.IDLE
        with pytest.raises(SessionAlreadyRunningError):
            session.start()

    def test_stop_transitions_to_stopped(self, session):
        """Stop should transition to STOPPED."""
        session.start()
        session.stop()
        assert session.state == SessionState.STOPPED
        assert session._terminate_called is True

    def test_stop_clears_pid(self, session):
        """Stop should clear PID."""
        session.start()
        session.stop()
        assert session.pid is None

    def test_stop_updates_metrics(self, session):
        """Stop should update stopped_at metric."""
        session.start()
        session.stop()
        assert session.metrics.stopped_at is not None

    def test_stop_idempotent(self, session):
        """Stopping a stopped session should be safe."""
        session.start()
        session.stop()
        session.stop()  # Should not raise
        assert session.state == SessionState.STOPPED

    def test_stop_force_flag(self, session):
        """Stop with force=True should pass to terminate."""
        session.start()
        session.stop(force=True)
        assert session._force_terminate is True

    def test_restart(self, session):
        """Restart should stop and start."""
        session.start()
        old_pid = session.pid
        session.restart()
        assert session.state == SessionState.IDLE
        # Would have new instance in real implementation

    def test_spawn_failure_crashes(self, session):
        """Spawn failure should transition to CRASHED."""
        session.set_should_fail_spawn(True)
        with pytest.raises(SessionSpawnError):
            session.start()
        assert session.state == SessionState.CRASHED
        assert session.metrics.errors_count == 1

    def test_restart_from_crashed(self, session):
        """Should be able to restart from crashed state."""
        session.set_should_fail_spawn(True)
        with pytest.raises(SessionSpawnError):
            session.start()
        assert session.state == SessionState.CRASHED

        # Now allow spawn to succeed
        session.set_should_fail_spawn(False)
        session.start()
        assert session.state == SessionState.IDLE


class TestSessionAliveReady:
    """Test is_alive and is_ready properties."""

    def test_stopped_not_alive(self, session):
        """STOPPED should not be alive."""
        assert session.state == SessionState.STOPPED
        assert session.is_alive is False

    def test_idle_is_alive(self, session):
        """IDLE should be alive."""
        session.start()
        assert session.is_alive is True

    def test_idle_is_ready(self, session):
        """IDLE should be ready."""
        session.start()
        assert session.is_ready is True

    def test_crashed_not_alive(self, session):
        """CRASHED should not be alive."""
        session.set_should_fail_spawn(True)
        with pytest.raises(SessionSpawnError):
            session.start()
        assert session.is_alive is False


class TestWorkerBinding:
    """Test worker binding functionality."""

    def test_bind_to_worker(self, session):
        """Should bind to worker."""
        session.bind_to_worker("worker-456")
        assert session.bound_worker_id == "worker-456"

    def test_rebind_same_worker_ok(self, session):
        """Rebinding to same worker should be fine."""
        session.bind_to_worker("worker-456")
        session.bind_to_worker("worker-456")  # Should not raise
        assert session.bound_worker_id == "worker-456"

    def test_rebind_different_worker_raises(self, session):
        """Rebinding to different worker should raise."""
        session.bind_to_worker("worker-456")
        with pytest.raises(SessionAlreadyBoundError) as exc_info:
            session.bind_to_worker("worker-789")
        assert exc_info.value.current_worker == "worker-456"
        assert exc_info.value.requested_worker == "worker-789"

    def test_verify_binding_true(self, session):
        """Verify binding returns True for bound worker."""
        session.bind_to_worker("worker-456")
        assert session.verify_binding("worker-456") is True

    def test_verify_binding_false(self, session):
        """Verify binding returns False for different worker."""
        session.bind_to_worker("worker-456")
        assert session.verify_binding("worker-789") is False

    def test_verify_binding_unbound(self, session):
        """Verify binding returns False when unbound."""
        assert session.verify_binding("worker-456") is False


class TestStateCallbacks:
    """Test state change callbacks."""

    def test_callback_on_state_change(self, session):
        """Callbacks should be called on state change."""
        changes = []

        def callback(old: SessionState, new: SessionState):
            changes.append((old, new))

        session.on_state_change(callback)
        session.start()

        # Should have recorded: STOPPED->STARTING, STARTING->RUNNING, RUNNING->IDLE
        assert len(changes) == 3
        assert changes[0] == (SessionState.STOPPED, SessionState.STARTING)
        assert changes[1] == (SessionState.STARTING, SessionState.RUNNING)
        assert changes[2] == (SessionState.RUNNING, SessionState.IDLE)

    def test_callback_error_does_not_break_state_machine(self, session):
        """Callback errors should not break state transitions."""
        def bad_callback(old: SessionState, new: SessionState):
            raise RuntimeError("Callback error!")

        session.on_state_change(bad_callback)
        session.start()  # Should not raise
        assert session.state == SessionState.IDLE


class TestSendPrompt:
    """Test send_prompt functionality."""

    def test_send_prompt_from_idle(self, session):
        """Should be able to send prompt from IDLE state."""
        session.start()
        session.set_responses(["Hello, world!"])
        session._complete_after_reads = 1
        result = session.send_prompt("Hello")

        assert result.prompt == "Hello"
        assert result.response.content == "Hello, world!"
        assert result.turn_id == "turn-1"

    def test_send_prompt_updates_metrics(self, session):
        """Send prompt should update metrics."""
        session.start()
        session.set_responses(["Response"])
        session._complete_after_reads = 1
        session.send_prompt("Test")

        assert session.metrics.prompts_sent == 1
        assert session.metrics.responses_received == 1
        assert session.metrics.last_activity is not None

    def test_send_prompt_returns_to_idle(self, session):
        """After send_prompt, should return to IDLE."""
        session.start()
        session.set_responses(["Response"])
        session._complete_after_reads = 1
        session.send_prompt("Test")

        assert session.state == SessionState.IDLE

    def test_send_prompt_not_ready_raises(self, session):
        """Sending prompt when not IDLE should raise."""
        # Session is STOPPED
        with pytest.raises(SessionNotReadyError) as exc_info:
            session.send_prompt("Test")
        assert exc_info.value.state == SessionState.STOPPED

    def test_multiple_prompts(self, session):
        """Should handle multiple prompts."""
        session.start()
        session.set_responses(["R1", "R2"])
        session._complete_after_reads = 1

        r1 = session.send_prompt("P1")
        session._read_count = 0
        r2 = session.send_prompt("P2")

        assert r1.turn_id == "turn-1"
        assert r2.turn_id == "turn-2"
        assert session.metrics.prompts_sent == 2


class TestCancel:
    """Test cancel functionality."""

    def test_cancel_from_running(self, session):
        """Cancel should interrupt and return to IDLE."""
        session.start()
        # Manually set to RUNNING to simulate mid-prompt
        session._state = SessionState.RUNNING
        session.cancel()
        assert session.state == SessionState.IDLE


# =========================================================================
# Exception Tests
# =========================================================================

class TestExceptions:
    """Test exception classes."""

    def test_session_error_message(self):
        """SessionError should format message with session ID."""
        session_id = SessionId(worker_id="w1", instance_id="i1")
        error = SessionError(session_id, "Test error")
        assert "w1:i1" in str(error)
        assert "Test error" in str(error)

    def test_spawn_error(self):
        """SessionSpawnError should include cause."""
        session_id = SessionId(worker_id="w1", instance_id="i1")
        error = SessionSpawnError(session_id, "Process failed")
        assert "Failed to spawn" in str(error)
        assert "Process failed" in str(error)
        assert error.cause == "Process failed"

    def test_already_running_error(self):
        """SessionAlreadyRunningError should indicate already running."""
        session_id = SessionId(worker_id="w1", instance_id="i1")
        error = SessionAlreadyRunningError(session_id)
        assert "Already running" in str(error)

    def test_not_running_error(self):
        """SessionNotRunningError should include current state."""
        session_id = SessionId(worker_id="w1", instance_id="i1")
        error = SessionNotRunningError(session_id, SessionState.STOPPED)
        assert "Not running" in str(error)
        assert "stopped" in str(error)
        assert error.state == SessionState.STOPPED

    def test_not_ready_error(self):
        """SessionNotReadyError should include current state."""
        session_id = SessionId(worker_id="w1", instance_id="i1")
        error = SessionNotReadyError(session_id, SessionState.RUNNING)
        assert "Not ready" in str(error)
        assert "running" in str(error)
        assert error.state == SessionState.RUNNING

    def test_timeout_error(self):
        """SessionTimeoutError should include operation and timeout."""
        session_id = SessionId(worker_id="w1", instance_id="i1")
        error = SessionTimeoutError(session_id, "startup", 30000)
        assert "startup" in str(error)
        assert "30000ms" in str(error)
        assert error.operation == "startup"
        assert error.timeout_ms == 30000

    def test_already_bound_error(self):
        """SessionAlreadyBoundError should include both workers."""
        session_id = SessionId(worker_id="w1", instance_id="i1")
        error = SessionAlreadyBoundError(session_id, "worker-A", "worker-B")
        assert "worker-A" in str(error)
        assert "worker-B" in str(error)
        assert error.current_worker == "worker-A"
        assert error.requested_worker == "worker-B"

    def test_invalid_state_transition(self):
        """InvalidSessionStateTransition should include details."""
        error = InvalidSessionStateTransition(
            SessionState.IDLE,
            SessionState.STARTING,
            [SessionState.RUNNING, SessionState.STOPPED]
        )
        assert "idle" in str(error)
        assert "starting" in str(error)
        assert error.current == SessionState.IDLE
        assert error.attempted == SessionState.STARTING


class TestStateValidation:
    """Test state transition validation."""

    def test_invalid_transition_from_stopped(self, session):
        """Cannot transition from STOPPED to invalid state."""
        assert session.state == SessionState.STOPPED
        with pytest.raises(InvalidSessionStateTransition):
            session._validate_state_transition(SessionState.IDLE)

    def test_valid_transition_from_stopped(self, session):
        """Can transition from STOPPED to STARTING."""
        assert session.state == SessionState.STOPPED
        session._validate_state_transition(SessionState.STARTING)  # Should not raise

    def test_invalid_transition_from_idle(self, session):
        """Cannot transition from IDLE to invalid state."""
        session.start()
        assert session.state == SessionState.IDLE
        with pytest.raises(InvalidSessionStateTransition):
            session._validate_state_transition(SessionState.STARTING)

"""
Tests for AgentSession - unified interface for AI agent sessions.
"""

import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from shared.pyterm.agent_session import AgentSession, AgentSessionConfig
from shared.pyterm.agent_state import AgentState
from shared.pyterm.protocols import ExtractedOutput, SessionState, WorkerState
from shared.pyterm.conversation import Message, ToolCall
from shared.pyterm.config import PytermConfig


class MockSession:
    """Mock session for testing."""

    def __init__(self, session_name: str = "test"):
        self._name = session_name
        self.injected: list[str] = []
        self.output_text = ""
        self._state = SessionState.IDLE
        self.start_called = False
        self.stop_called = False

    @property
    def id(self) -> str:
        return f"mock-{self._name}"

    @property
    def state(self) -> SessionState:
        return self._state

    def start(self, config=None) -> None:
        self.start_called = True
        self._state = SessionState.RUNNING

    def stop(self, force: bool = False) -> None:
        self.stop_called = True
        self._state = SessionState.EXITED

    def inject(self, text: str) -> None:
        self.injected.append(text)

    def extract(self) -> ExtractedOutput:
        return ExtractedOutput(text=self.output_text, timestamp=time.time())

    def set_output(self, text: str) -> None:
        self.output_text = text


class TestAgentSessionConfig:
    """Tests for AgentSessionConfig."""

    def test_config_with_explicit_pyterm_config(self):
        pyterm_config = PytermConfig.standard()
        config = AgentSessionConfig(
            worker_id="test-worker",
            pyterm_config=pyterm_config,
        )
        assert config.worker_id == "test-worker"
        assert config.session_name is None
        assert config.provider == "claude_code"
        assert config.db_path is None
        assert config.auto_persist is True
        assert config.pyterm_config is pyterm_config

    def test_config_create_factory(self):
        config = AgentSessionConfig.create(worker_id="test-worker")
        assert config.worker_id == "test-worker"
        assert config.pyterm_config is not None

    def test_config_custom(self):
        config = AgentSessionConfig.create(
            worker_id="w1",
            session_name="my-session",
            provider="generic",
            db_path=Path("/tmp/test.db"),
            auto_persist=False,
        )
        assert config.session_name == "my-session"
        assert config.provider == "generic"
        assert config.auto_persist is False


class TestAgentSessionFactory:
    """Tests for AgentSession.create factory method."""

    def test_create_minimal(self):
        session = AgentSession.create("worker-1")
        assert session.worker_id == "worker-1"
        assert session.provider == "claude-code"  # Provider returns canonical name

    def test_create_with_options(self):
        session = AgentSession.create(
            worker_id="w2",
            provider="generic",
            session_name="custom-session",
            auto_persist=False,
        )
        assert session.worker_id == "w2"
        assert session.provider == "generic"


class TestAgentSessionLifecycle:
    """Tests for session lifecycle methods."""

    def test_start_session(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        agent.start()

        assert mock_session.start_called
        assert agent.is_running

    def test_stop_session(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        agent.start()
        agent.stop()

        assert mock_session.stop_called

    def test_restart_session(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        agent.start()
        mock_session.start_called = False  # Reset flag
        agent.restart()

        assert mock_session.stop_called
        assert mock_session.start_called

    def test_is_running_property(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        assert not agent.is_running
        agent.start()
        assert agent.is_running

    def test_session_state_property(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        assert agent.session_state == SessionState.IDLE
        agent.start()
        assert agent.session_state == SessionState.RUNNING


class TestAgentSessionState:
    """Tests for agent state properties."""

    def test_initial_state(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        assert agent.state == AgentState.IDLE
        assert agent.is_idle is True
        assert agent.is_paused is False

    def test_state_after_transition(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        # Force state transition
        agent._controller._state_machine.force_transition(AgentState.THINKING)
        assert agent.state == AgentState.THINKING
        assert agent.is_idle is False


class TestAgentSessionWorkerState:
    """Tests for worker lifecycle state."""

    def test_initial_worker_state(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        assert agent.worker_state == WorkerState.PENDING

    def test_worker_state_after_start(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        agent.start()
        assert agent.worker_state == WorkerState.ONBOARDING

    def test_activate_worker(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        agent.start()
        assert agent.activate()
        assert agent.worker_state == WorkerState.ACTIVE

    def test_worker_state_after_stop(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        agent.start()
        agent.stop()
        assert agent.worker_state == WorkerState.TERMINATED


class TestAgentSessionPauseResume:
    """Tests for pause/resume functionality."""

    def test_pause(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        assert agent.pause()
        assert agent.is_paused

    def test_resume(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        agent.pause()
        assert agent.resume()
        assert agent.is_idle


class TestAgentSessionTranscript:
    """Tests for transcript access."""

    def test_transcript_property(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        assert len(agent.transcript) == 0

        # Add a turn
        turn = agent.transcript.new_turn("Hello")
        turn.complete(Message.assistant("Hi there"))

        assert len(agent.transcript) == 1

    def test_get_messages(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        turn = agent.transcript.new_turn("Hello")
        turn.complete(Message.assistant("Hi"))

        messages = agent.get_messages()
        assert len(messages) == 2  # user + assistant

    def test_get_turn(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        turn = agent.transcript.new_turn("Hello")
        found = agent.get_turn(turn.id)
        assert found == turn

    def test_current_turn(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        assert agent.current_turn() is None

        turn = agent.transcript.new_turn("Hello")
        assert agent.current_turn() == turn


class TestAgentSessionToolTracking:
    """Tests for tool tracking."""

    def test_tool_tracker_property(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        tc = ToolCall(id="tc1", name="bash", arguments={"cmd": "ls"})
        agent.tool_tracker.add_call(tc)

        assert agent.tool_tracker.total_calls == 1

    def test_get_tool_calls(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        turn = agent.transcript.new_turn("Do something")
        tc = ToolCall(id="tc1", name="bash", arguments={})
        turn.add_tool_call(tc)

        calls = agent.get_tool_calls()
        assert len(calls) == 1


class TestAgentSessionOutput:
    """Tests for output inspection."""

    def test_get_raw_output(self):
        mock_session = MockSession()
        mock_session.set_output("Hello world")
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        assert agent.get_raw_output() == "Hello world"

    def test_get_current_output(self):
        mock_session = MockSession()
        mock_session.set_output("Some output")
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        parsed = agent.get_current_output()
        assert parsed.raw == "Some output"


class TestAgentSessionCallbacks:
    """Tests for callback registration."""

    def test_on_state_change(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        states = []
        agent.on_state_change(lambda old, new: states.append((old, new)))

        agent._controller._state_machine.transition(AgentState.THINKING)
        assert len(states) == 1
        assert states[0] == (AgentState.IDLE, AgentState.THINKING)

    def test_on_response(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        responses = []
        agent.on_response(lambda r: responses.append(r))

        assert len(agent._controller._response_callbacks) == 1


class TestAgentSessionReset:
    """Tests for reset functionality."""

    def test_reset(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        # Add some state
        agent.transcript.new_turn("Test")
        agent._controller._state_machine.force_transition(AgentState.THINKING)

        # Reset
        agent.reset()

        assert len(agent.transcript) == 0
        assert agent.is_idle

    def test_clear_transcript(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        agent.transcript.new_turn("Test")
        assert len(agent.transcript) == 1

        agent.clear_transcript()
        assert len(agent.transcript) == 0


class TestAgentSessionSerialization:
    """Tests for serialization."""

    def test_worker_id_property(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="my-worker")
        agent = AgentSession(config, session=mock_session)

        assert agent.worker_id == "my-worker"

    def test_provider_property(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test", provider="generic")
        agent = AgentSession(config, session=mock_session)

        assert agent.provider == "generic"

    def test_to_dict(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        d = agent.to_dict()

        assert d["worker_id"] == "test"
        assert d["provider"] == "claude-code"  # Provider returns canonical name
        assert d["agent_state"] == "idle"
        assert d["is_idle"] is True
        assert d["has_persistence"] is False
        assert "transcript" in d
        assert "tool_tracker" in d


class TestAgentSessionContextManager:
    """Tests for context manager support."""

    def test_context_manager(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test")
        agent = AgentSession(config, session=mock_session)

        with agent as a:
            assert a.is_running

        assert mock_session.stop_called


class TestAgentSessionPersistence:
    """Tests for persistence functionality."""

    def test_save_without_store(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test", db_path=None)
        agent = AgentSession(config, session=mock_session)

        assert agent.save() is False

    def test_load_without_store(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test", db_path=None)
        agent = AgentSession(config, session=mock_session)

        assert agent.load() is False

    def test_delete_history_without_store(self):
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="test", db_path=None)
        agent = AgentSession(config, session=mock_session)

        assert agent.delete_history() is False

    def test_save_with_store(self, tmp_path):
        mock_session = MockSession()
        db_path = tmp_path / "test.db"
        config = AgentSessionConfig.create(worker_id="test", db_path=db_path)
        agent = AgentSession(config, session=mock_session)

        # Add some content
        turn = agent.transcript.new_turn("Hello")
        turn.complete(Message.assistant("Hi"))

        assert agent.save() is True

    def test_load_with_store(self, tmp_path):
        mock_session = MockSession()
        db_path = tmp_path / "test.db"

        # Create and save
        config1 = AgentSessionConfig.create(worker_id="test", db_path=db_path)
        agent1 = AgentSession(config1, session=mock_session)
        turn = agent1.transcript.new_turn("Hello")
        turn.complete(Message.assistant("Hi"))
        agent1.save()

        # Load in new session
        config2 = AgentSessionConfig.create(worker_id="test", db_path=db_path)
        agent2 = AgentSession(config2, session=MockSession())
        assert agent2.load() is True
        assert len(agent2.transcript) == 1


class TestAgentSessionIntegration:
    """Integration tests."""

    def test_full_session_flow(self):
        """Test a complete session flow without actual tmux."""
        mock_session = MockSession()
        config = AgentSessionConfig.create(worker_id="integration-test")
        agent = AgentSession(config, session=mock_session)

        # Start session
        agent.start()
        assert agent.is_running
        assert agent.is_idle

        # Add transcript entries manually
        turn1 = agent.transcript.new_turn("What is 2+2?")
        turn1.complete(Message.assistant("4"))

        turn2 = agent.transcript.new_turn("Thanks!")
        turn2.complete(Message.assistant("You're welcome!"))

        # Check state
        assert len(agent.transcript) == 2
        assert len(agent.get_messages()) == 4

        # Stop
        agent.stop()

    def test_session_with_persistence(self, tmp_path):
        """Test session with SQLite persistence."""
        db_path = tmp_path / "agent.db"

        # Create first session
        mock1 = MockSession()
        config1 = AgentSessionConfig.create(
            worker_id="persist-test",
            db_path=db_path,
            auto_persist=False,
        )
        agent1 = AgentSession(config1, session=mock1)

        turn = agent1.transcript.new_turn("Remember this")
        turn.complete(Message.assistant("I will remember"))
        agent1.save()

        # Create second session and load
        mock2 = MockSession()
        config2 = AgentSessionConfig.create(
            worker_id="persist-test",
            db_path=db_path,
        )
        agent2 = AgentSession(config2, session=mock2)
        assert agent2.load()

        assert len(agent2.transcript) == 1
        assert agent2.transcript.current_turn().prompt.content == "Remember this"

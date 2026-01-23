"""
Tests for wrkr session integration.

Tests the SessionWorker, adapters, and session lifecycle management.
"""

import pytest
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from shared.wrkr.core.config import WorkerConfig
from shared.wrkr.core.result import WorkerResult
from shared.wrkr.core.state import WorkerState
from shared.wrkr.core.task import Task
from shared.wrkr.session.adapter import DefaultPromptBuilder, ResultExtractor
from shared.wrkr.session.worker import SessionWorker, create_session_worker


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def worker_config():
    """Create a test worker config."""
    return WorkerConfig(
        id="test-worker-1",
        name="Test Worker",
        skills={"coding": 80, "reasoning": 70},
        cost=50,
        idle_behavior="exit",  # Exit immediately when queue is empty
    )


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id="task-1",
        title="Implement feature X",
        description="Add the new feature X to the codebase",
        priority=2,
        ask_id="ask-123",
        okr_id="okr-456",
        metadata={"component": "backend"},
    )


@dataclass
class MockTurn:
    """Mock Turn object for testing."""
    id: str = "turn-1"
    response: Any = None
    tool_calls: list = field(default_factory=list)


@dataclass
class MockResponse:
    """Mock response object."""
    content: str = ""


@dataclass
class MockPromptResult:
    """Mock PromptResult for testing."""
    turn: MockTurn | None = None
    final_state: str = "idle"
    duration_ms: int = 1000
    was_cancelled: bool = False
    error: str | None = None


class MockSession:
    """Mock AgentSession for testing."""

    def __init__(self):
        self.started = False
        self.stopped = False
        self.prompts_sent: list[tuple[str, dict]] = []
        self._response_content = "Task completed successfully."
        self._should_timeout = False
        self._should_error = False

    def start(self):
        self.started = True

    def stop(self, force: bool = False):
        self.stopped = True

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        return True

    def send_prompt(self, prompt: str, timeout: float | None = None, **metadata) -> MockPromptResult:
        self.prompts_sent.append((prompt, metadata))

        if self._should_timeout:
            from shared.wrkr.session.worker import TimeoutError
            raise TimeoutError("Timed out")

        if self._should_error:
            raise RuntimeError("Session error")

        turn = MockTurn(
            response=MockResponse(content=self._response_content),
            tool_calls=[],
        )
        return MockPromptResult(turn=turn, duration_ms=500)

    def set_response(self, content: str):
        self._response_content = content

    def set_timeout(self):
        self._should_timeout = True

    def set_error(self):
        self._should_error = True


class MockQueue:
    """Mock queue for testing."""

    def __init__(self):
        self._tasks: list[Task] = []
        self._done: list[str] = []
        self._blocked: list[tuple[str, str]] = []

    def push(self, task: Task):
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: t.priority)

    def pop_highest_priority(self) -> Task | None:
        if not self._tasks:
            return None
        return self._tasks.pop(0)

    def mark_done(self, task_id: str):
        self._done.append(task_id)

    def mark_blocked(self, task_id: str, reason: str):
        self._blocked.append((task_id, reason))


class MockMemory:
    """Mock memory for testing."""

    def __init__(self):
        self._records: list[dict] = []

    def record(self, task: Task, result: WorkerResult):
        self._records.append({"task": task, "result": result})

    def recent(self, limit: int = 10) -> list[dict]:
        return self._records[-limit:]

    def get_context(self, task: Task) -> dict:
        return {"similar_tasks": [], "guidance": "No specific guidance."}


class MockEscalation:
    """Mock escalation for testing."""

    def __init__(self, resolve: bool = True):
        self._resolve = resolve
        self.asks: list[tuple[str, dict]] = []

    def ask(self, issue: str, context: dict) -> Any:
        self.asks.append((issue, context))

        @dataclass
        class Response:
            resolved: bool
            guidance: str = ""
            new_tasks: list = field(default_factory=list)

        return Response(resolved=self._resolve, guidance="Mock guidance")

    def can_handle(self, issue: str) -> bool:
        return True


# =============================================================================
# DefaultPromptBuilder Tests
# =============================================================================


class TestDefaultPromptBuilder:
    """Tests for DefaultPromptBuilder."""

    def test_build_basic_prompt(self, sample_task):
        builder = DefaultPromptBuilder()
        prompt = builder.build(sample_task)

        assert "Implement feature X" in prompt
        assert "Add the new feature X" in prompt
        assert "MEDIUM" in prompt  # Priority 2

    def test_build_includes_ask_okr(self, sample_task):
        builder = DefaultPromptBuilder()
        prompt = builder.build(sample_task)

        assert "ask-123" in prompt
        assert "okr-456" in prompt

    def test_build_includes_metadata(self, sample_task):
        builder = DefaultPromptBuilder(include_metadata=True)
        prompt = builder.build(sample_task)

        assert "component" in prompt
        assert "backend" in prompt

    def test_build_excludes_metadata_when_disabled(self, sample_task):
        builder = DefaultPromptBuilder(include_metadata=False)
        prompt = builder.build(sample_task)

        # Should still have task info but not metadata section
        assert "Implement feature X" in prompt

    def test_build_includes_context(self, sample_task):
        builder = DefaultPromptBuilder(include_context=True)
        context = {
            "similar_tasks": [
                {"task_title": "Similar task", "result_succeeded": True}
            ],
            "guidance": "Use the existing pattern from module Y",
        }
        prompt = builder.build(sample_task, context)

        assert "Similar task" in prompt
        assert "Use the existing pattern" in prompt

    def test_build_high_priority(self):
        task = Task(id="t1", title="Urgent", description="Critical issue", priority=0)
        builder = DefaultPromptBuilder()
        prompt = builder.build(task)

        assert "CRITICAL" in prompt

    def test_build_low_priority(self):
        task = Task(id="t1", title="Backlog item", description="Low priority work", priority=4)
        builder = DefaultPromptBuilder()
        prompt = builder.build(task)

        assert "BACKLOG" in prompt


# =============================================================================
# ResultExtractor Tests
# =============================================================================


class TestResultExtractor:
    """Tests for ResultExtractor."""

    def test_extract_success(self, sample_task):
        extractor = ResultExtractor()
        turn = MockTurn(response=MockResponse(content="Task completed successfully."))
        prompt_result = MockPromptResult(turn=turn, duration_ms=1000)

        result = extractor.extract(prompt_result, sample_task)

        assert result.succeeded
        assert "completed" in result.output.lower()
        assert result.duration_ms == 1000

    def test_extract_cancelled(self, sample_task):
        extractor = ResultExtractor()
        prompt_result = MockPromptResult(was_cancelled=True, duration_ms=500)

        result = extractor.extract(prompt_result, sample_task)

        assert not result.succeeded
        assert "cancelled" in result.error.lower()

    def test_extract_error(self, sample_task):
        extractor = ResultExtractor()
        prompt_result = MockPromptResult(error="Connection failed", duration_ms=100)

        result = extractor.extract(prompt_result, sample_task)

        assert not result.succeeded
        assert "Connection failed" in result.error

    def test_extract_escalation_needed(self, sample_task):
        extractor = ResultExtractor()
        turn = MockTurn(
            response=MockResponse(
                content="I cannot proceed because I need help with the database schema."
            )
        )
        prompt_result = MockPromptResult(turn=turn, duration_ms=800)

        result = extractor.extract(prompt_result, sample_task)

        assert result.needs_escalation
        assert "cannot proceed" in result.escalation_reason.lower()

    def test_extract_blocked_keyword(self, sample_task):
        extractor = ResultExtractor()
        turn = MockTurn(
            response=MockResponse(content="I am blocked by missing API credentials.")
        )
        prompt_result = MockPromptResult(turn=turn)

        result = extractor.extract(prompt_result, sample_task)

        assert result.needs_escalation

    def test_extract_with_tool_calls(self, sample_task):
        extractor = ResultExtractor()

        @dataclass
        class MockToolCall:
            name: str
            arguments: dict

        turn = MockTurn(
            response=MockResponse(content="Done successfully."),
            tool_calls=[
                MockToolCall(name="Read", arguments={"file_path": "test.py"}),
                MockToolCall(name="Write", arguments={"file_path": "output.py"}),
            ],
        )
        prompt_result = MockPromptResult(turn=turn)

        result = extractor.extract(prompt_result, sample_task)

        assert result.succeeded
        assert len(result.artifacts) == 2
        assert result.artifacts[0] == "test.py"
        assert result.artifacts[1] == "output.py"

    def test_custom_escalation_keywords(self, sample_task):
        extractor = ResultExtractor(escalation_keywords=["custom_block"])
        turn = MockTurn(response=MockResponse(content="Hit a custom_block here."))
        prompt_result = MockPromptResult(turn=turn)

        result = extractor.extract(prompt_result, sample_task)

        assert result.needs_escalation


# =============================================================================
# SessionWorker Tests
# =============================================================================


class TestSessionWorkerInitialization:
    """Tests for SessionWorker initialization."""

    def test_create_worker(self, worker_config):
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: MockSession(),
        )

        assert worker.state == WorkerState.PENDING
        assert not worker.has_session

    def test_factory_function(self, worker_config):
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = create_session_worker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: MockSession(),
        )

        assert isinstance(worker, SessionWorker)


class TestSessionWorkerOnboarding:
    """Tests for SessionWorker onboarding/session creation."""

    def test_onboard_creates_session(self, worker_config):
        session = MockSession()
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        # Transition to onboarding triggers _onboard()
        worker.transition_to(WorkerState.ONBOARDING)
        worker._onboard()

        assert worker.has_session
        assert session.started

    def test_session_started_during_run(self, worker_config):
        session = MockSession()
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        # Empty queue so run() exits immediately
        worker.run()

        assert session.started


class TestSessionWorkerExecution:
    """Tests for SessionWorker task execution."""

    def test_execute_sends_prompt(self, worker_config, sample_task):
        session = MockSession()
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        # Manually onboard
        worker.transition_to(WorkerState.ONBOARDING)
        worker._onboard()
        worker.transition_to(WorkerState.ACTIVE)

        result = worker.execute(sample_task)

        assert len(session.prompts_sent) == 1
        prompt, metadata = session.prompts_sent[0]
        assert "Implement feature X" in prompt
        assert metadata["task_id"] == "task-1"

    def test_execute_returns_success(self, worker_config, sample_task):
        session = MockSession()
        session.set_response("Task completed successfully.")
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        worker.transition_to(WorkerState.ONBOARDING)
        worker._onboard()
        worker.transition_to(WorkerState.ACTIVE)

        result = worker.execute(sample_task)

        assert result.succeeded

    def test_execute_handles_timeout(self, worker_config, sample_task):
        session = MockSession()
        session.set_timeout()
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        worker.transition_to(WorkerState.ONBOARDING)
        worker._onboard()
        worker.transition_to(WorkerState.ACTIVE)

        result = worker.execute(sample_task)

        assert result.needs_escalation
        assert "timed out" in result.escalation_reason.lower()

    def test_execute_handles_session_error(self, worker_config, sample_task):
        session = MockSession()
        session.set_error()
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        worker.transition_to(WorkerState.ONBOARDING)
        worker._onboard()
        worker.transition_to(WorkerState.ACTIVE)

        result = worker.execute(sample_task)

        assert not result.succeeded
        assert "Session error" in result.error

    def test_execute_without_session_fails(self, worker_config, sample_task):
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: MockSession(),
        )

        # Don't onboard - no session
        result = worker.execute(sample_task)

        assert not result.succeeded
        assert "No active session" in result.error


class TestSessionWorkerLifecycle:
    """Tests for SessionWorker lifecycle management."""

    def test_session_cleaned_on_termination(self, worker_config):
        session = MockSession()
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        # Run through lifecycle
        worker.run()

        assert session.stopped
        assert not worker.has_session

    def test_full_task_execution(self, worker_config, sample_task):
        session = MockSession()
        session.set_response("Task completed successfully.")
        queue = MockQueue()
        queue.push(sample_task)
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        worker.run()

        # Task should be processed
        assert "task-1" in queue._done
        # Memory should record result
        assert len(memory._records) == 1
        assert memory._records[0]["result"].succeeded


class TestSessionWorkerWithContext:
    """Tests for SessionWorker with memory context."""

    def test_context_included_in_prompt(self, worker_config, sample_task):
        session = MockSession()
        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = SessionWorker(
            config=worker_config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=lambda c: session,
        )

        worker.transition_to(WorkerState.ONBOARDING)
        worker._onboard()
        worker.transition_to(WorkerState.ACTIVE)

        worker.execute(sample_task)

        prompt, _ = session.prompts_sent[0]
        assert "Additional Context" in prompt or "No specific guidance" in prompt

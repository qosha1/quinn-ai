"""Tests for the BaseWorker class.

Tests worker lifecycle, state transitions, task handling, escalation, and idle behavior.
Uses a concrete SimpleWorker subclass that implements execute().
"""

import pytest

from wrkr.core.config import WorkerConfig
from wrkr.core.result import WorkerResult
from wrkr.core.state import InvalidTransition, WorkerState
from wrkr.core.task import Task
from wrkr.core.worker import BaseWorker, EscalationResponse
from wrkr.escalation.interface import MockEscalation
from wrkr.memory.interface import MockMemory
from wrkr.queue.interface import MockQueue


class SimpleWorker(BaseWorker):
    """Concrete worker implementation for testing.

    Returns success for all tasks by default. Can be configured to return
    specific results for testing different scenarios.
    """

    def __init__(
        self,
        config: WorkerConfig,
        queue: MockQueue,
        memory: MockMemory,
        escalation: MockEscalation,
        result_to_return: WorkerResult | None = None,
        raise_exception: Exception | None = None,
    ) -> None:
        super().__init__(config, queue, memory, escalation)
        self._result_to_return = result_to_return
        self._raise_exception = raise_exception
        self.executed_tasks: list[Task] = []
        self.state_changes: list[WorkerState] = []

    def execute(self, task: Task) -> WorkerResult:
        """Execute a task. Records the task and returns configured result."""
        self.executed_tasks.append(task)

        if self._raise_exception is not None:
            raise self._raise_exception

        if self._result_to_return is not None:
            return self._result_to_return

        return WorkerResult.success(f"Completed task: {task.title}")

    def _on_state_change(self, new_state: WorkerState) -> None:
        """Record state changes for testing."""
        self.state_changes.append(new_state)


@pytest.fixture
def test_worker(
    sample_config: WorkerConfig,
    mock_queue: MockQueue,
    mock_memory: MockMemory,
    mock_escalation: MockEscalation,
) -> SimpleWorker:
    """Create a SimpleWorker with default configuration."""
    return SimpleWorker(
        config=sample_config,
        queue=mock_queue,
        memory=mock_memory,
        escalation=mock_escalation,
    )


class TestWorkerInitialization:
    """Tests for worker initialization."""

    def test_initial_state_is_pending(self, test_worker: SimpleWorker) -> None:
        """Worker starts in PENDING state."""
        assert test_worker.state == WorkerState.PENDING

    def test_config_accessible(self, test_worker: SimpleWorker, sample_config: WorkerConfig) -> None:
        """Worker config is accessible via property."""
        assert test_worker.config == sample_config
        assert test_worker.config.id == "worker-001"

    def test_should_stop_initially_false(self, test_worker: SimpleWorker) -> None:
        """Worker should_stop flag is initially False."""
        assert test_worker._should_stop is False


class TestStateTransitions:
    """Tests for worker state transitions."""

    def test_transition_to_onboarding(self, test_worker: SimpleWorker) -> None:
        """Worker can transition from PENDING to ONBOARDING."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        assert test_worker.state == WorkerState.ONBOARDING

    def test_transition_to_active(self, test_worker: SimpleWorker) -> None:
        """Worker can transition PENDING -> ONBOARDING -> ACTIVE."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)
        assert test_worker.state == WorkerState.ACTIVE

    def test_transition_to_working(self, test_worker: SimpleWorker) -> None:
        """Worker can transition to WORKING from ACTIVE."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)
        test_worker.transition_to(WorkerState.WORKING)
        assert test_worker.state == WorkerState.WORKING

    def test_transition_to_stuck(self, test_worker: SimpleWorker) -> None:
        """Worker can transition to STUCK from ACTIVE."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)
        test_worker.transition_to(WorkerState.STUCK)
        assert test_worker.state == WorkerState.STUCK

    def test_transition_to_offboarding(self, test_worker: SimpleWorker) -> None:
        """Worker can transition to OFFBOARDING from ACTIVE."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)
        test_worker.transition_to(WorkerState.OFFBOARDING)
        assert test_worker.state == WorkerState.OFFBOARDING

    def test_transition_to_terminated(self, test_worker: SimpleWorker) -> None:
        """Worker can transition to TERMINATED from OFFBOARDING."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)
        test_worker.transition_to(WorkerState.OFFBOARDING)
        test_worker.transition_to(WorkerState.TERMINATED)
        assert test_worker.state == WorkerState.TERMINATED

    def test_invalid_transition_raises(self, test_worker: SimpleWorker) -> None:
        """Invalid state transition raises InvalidTransition."""
        with pytest.raises(InvalidTransition):
            test_worker.transition_to(WorkerState.ACTIVE)  # Can't go PENDING -> ACTIVE

    def test_state_change_hook_called(self, test_worker: SimpleWorker) -> None:
        """_on_state_change hook is called on transitions."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        assert WorkerState.ONBOARDING in test_worker.state_changes

        test_worker.transition_to(WorkerState.ACTIVE)
        assert WorkerState.ACTIVE in test_worker.state_changes


class TestWorkerRun:
    """Tests for the worker run() method."""

    def test_run_with_empty_queue_exits(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
    ) -> None:
        """Worker with idle_behavior='exit' terminates on empty queue."""
        # sample_config has idle_behavior="exit"
        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
        )

        worker.run()

        assert worker.state == WorkerState.TERMINATED
        assert WorkerState.ONBOARDING in worker.state_changes
        assert WorkerState.ACTIVE in worker.state_changes
        assert WorkerState.OFFBOARDING in worker.state_changes
        assert WorkerState.TERMINATED in worker.state_changes

    def test_run_processes_single_task(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
        sample_task: Task,
    ) -> None:
        """Worker processes a task from the queue."""
        mock_queue.push(sample_task)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
        )

        worker.run()

        assert sample_task in worker.executed_tasks
        assert worker.state == WorkerState.TERMINATED

    def test_run_processes_multiple_tasks(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
    ) -> None:
        """Worker processes multiple tasks in order."""
        tasks = [
            Task(id=f"task-{i}", title=f"Task {i}", description=f"Desc {i}")
            for i in range(3)
        ]
        for task in tasks:
            mock_queue.push(task)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
        )

        worker.run()

        assert len(worker.executed_tasks) == 3
        assert worker.state == WorkerState.TERMINATED


class TestTaskHandling:
    """Tests for task execution and result handling."""

    def test_successful_task_marked_done(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
        sample_task: Task,
    ) -> None:
        """Successful task is marked as done in queue."""
        mock_queue.push(sample_task)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
        )

        worker.run()

        assert sample_task.id in mock_queue._done

    def test_successful_task_recorded_in_memory(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
        sample_task: Task,
    ) -> None:
        """Successful task execution is recorded in memory."""
        mock_queue.push(sample_task)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
        )

        worker.run()

        records = mock_memory.recent(limit=1)
        assert len(records) == 1
        assert records[0]["task_id"] == sample_task.id
        assert records[0]["result_succeeded"] is True

    def test_failed_task_marked_blocked(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
        sample_task: Task,
    ) -> None:
        """Failed task (no escalation) is marked as blocked."""
        mock_queue.push(sample_task)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
            result_to_return=WorkerResult.failure("Something went wrong"),
        )

        worker.run()

        assert sample_task.id in mock_queue._blocked
        _, reason = mock_queue._blocked[sample_task.id]
        assert reason == "Something went wrong"

    def test_exception_in_execute_creates_failure_result(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
        sample_task: Task,
    ) -> None:
        """Exception in execute() creates a failure result."""
        mock_queue.push(sample_task)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
            raise_exception=ValueError("Test error"),
        )

        worker.run()

        assert sample_task.id in mock_queue._blocked
        records = mock_memory.recent(limit=1)
        assert records[0]["result_succeeded"] is False
        assert "Test error" in records[0]["result_error"]


class TestEscalationFlow:
    """Tests for escalation handling."""

    def test_escalation_triggers_stuck_state(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
        sample_task: Task,
    ) -> None:
        """Task requiring escalation transitions worker to STUCK."""
        mock_queue.push(sample_task)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
            result_to_return=WorkerResult.escalate("Need help"),
        )

        worker.run()

        assert WorkerState.STUCK in worker.state_changes

    def test_resolved_escalation_marks_task_done(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        sample_task: Task,
    ) -> None:
        """Resolved escalation marks task as done."""
        mock_queue.push(sample_task)
        mock_escalation = MockEscalation(resolve_issues=True)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
            result_to_return=WorkerResult.escalate("Need help"),
        )

        worker.run()

        assert sample_task.id in mock_queue._done

    def test_unresolved_escalation_marks_task_blocked(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        sample_task: Task,
    ) -> None:
        """Unresolved escalation marks task as blocked."""
        mock_queue.push(sample_task)
        mock_escalation = MockEscalation(resolve_issues=False)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
            result_to_return=WorkerResult.escalate("Need help"),
        )

        worker.run()

        assert sample_task.id in mock_queue._blocked

    def test_escalation_records_ask(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        sample_task: Task,
    ) -> None:
        """Escalation calls the escalation interface."""
        mock_queue.push(sample_task)
        mock_escalation = MockEscalation(resolve_issues=True)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
            result_to_return=WorkerResult.escalate("Need manager help"),
        )

        worker.run()

        assert len(mock_escalation.asks) == 1
        issue, context = mock_escalation.asks[0]
        assert issue == "Need manager help"
        assert context["worker_id"] == sample_config.id

    def test_escalation_with_new_tasks(
        self,
        sample_config: WorkerConfig,
        mock_memory: MockMemory,
        sample_task: Task,
    ) -> None:
        """Escalation can add new tasks to the queue."""
        mock_queue = MockQueue()
        mock_queue.push(sample_task)

        new_task = Task(id="new-task", title="New Task", description="From escalation")

        # Custom escalation that returns new tasks (only once)
        class EscalationWithTasks(MockEscalation):
            def __init__(self) -> None:
                super().__init__()
                self._called = False

            def ask(self, issue: str, context: dict) -> EscalationResponse:
                if not self._called:
                    self._called = True
                    return EscalationResponse(
                        resolved=True,
                        guidance="Here's a new task",
                        new_tasks=[new_task],
                    )
                return EscalationResponse(resolved=True, guidance="")

        # Custom worker that only escalates on first task
        escalated_task_ids: set[str] = set()

        class EscalatingWorker(SimpleWorker):
            def execute(self, task: Task) -> WorkerResult:
                self.executed_tasks.append(task)
                if task.id not in escalated_task_ids:
                    escalated_task_ids.add(task.id)
                    if task.id == sample_task.id:
                        return WorkerResult.escalate("Need help")
                return WorkerResult.success(f"Completed: {task.title}")

        worker = EscalatingWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=EscalationWithTasks(),
        )

        worker.run()

        # New task should be in executed tasks (processed after escalation added it)
        assert new_task in worker.executed_tasks


class TestStopMethod:
    """Tests for the stop() method."""

    def test_stop_sets_should_stop_flag(self, test_worker: SimpleWorker) -> None:
        """stop() sets the should_stop flag."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)

        test_worker.stop()

        assert test_worker._should_stop is True

    def test_stop_transitions_to_offboarding(self, test_worker: SimpleWorker) -> None:
        """stop() transitions from ACTIVE to OFFBOARDING."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)

        test_worker.stop()

        assert test_worker.state == WorkerState.OFFBOARDING

    def test_stop_from_working(self, test_worker: SimpleWorker) -> None:
        """stop() can transition from WORKING to OFFBOARDING."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)
        test_worker.transition_to(WorkerState.WORKING)

        test_worker.stop()

        assert test_worker.state == WorkerState.OFFBOARDING

    def test_stop_from_stuck(self, test_worker: SimpleWorker) -> None:
        """stop() can transition from STUCK to OFFBOARDING."""
        test_worker.transition_to(WorkerState.ONBOARDING)
        test_worker.transition_to(WorkerState.ACTIVE)
        test_worker.transition_to(WorkerState.STUCK)

        test_worker.stop()

        assert test_worker.state == WorkerState.OFFBOARDING


class TestIdleBehavior:
    """Tests for idle behavior when queue is empty."""

    def test_idle_exit_terminates(
        self,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
    ) -> None:
        """idle_behavior='exit' causes termination on empty queue."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            idle_behavior="exit",
        )

        worker = SimpleWorker(
            config=config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
        )

        worker.run()

        assert worker.state == WorkerState.TERMINATED


class TestDurationTracking:
    """Tests for execution duration tracking."""

    def test_duration_set_if_not_in_result(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
        sample_task: Task,
    ) -> None:
        """Duration is set by worker if result doesn't have one."""
        mock_queue.push(sample_task)

        # Return result without duration_ms
        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
            result_to_return=WorkerResult.success("Done"),
        )

        worker.run()

        records = mock_memory.recent(limit=1)
        assert records[0]["result_duration_ms"] is not None
        assert records[0]["result_duration_ms"] >= 0

    def test_duration_preserved_if_in_result(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
        sample_task: Task,
    ) -> None:
        """Duration from result is preserved if already set."""
        mock_queue.push(sample_task)

        # Return result with specific duration_ms
        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
            result_to_return=WorkerResult.success("Done", duration_ms=999),
        )

        worker.run()

        records = mock_memory.recent(limit=1)
        assert records[0]["result_duration_ms"] == 999


class TestPriorityProcessing:
    """Tests for priority-based task processing."""

    def test_high_priority_processed_first(
        self,
        sample_config: WorkerConfig,
        mock_queue: MockQueue,
        mock_memory: MockMemory,
        mock_escalation: MockEscalation,
    ) -> None:
        """Higher priority tasks are processed before lower priority."""
        low_task = Task(id="low", title="Low", description="Low priority", priority=4)
        high_task = Task(id="high", title="High", description="High priority", priority=0)
        mid_task = Task(id="mid", title="Mid", description="Mid priority", priority=2)

        # Push in reverse priority order
        mock_queue.push(low_task)
        mock_queue.push(mid_task)
        mock_queue.push(high_task)

        worker = SimpleWorker(
            config=sample_config,
            queue=mock_queue,
            memory=mock_memory,
            escalation=mock_escalation,
        )

        worker.run()

        # Should be processed high -> mid -> low
        assert worker.executed_tasks[0].id == "high"
        assert worker.executed_tasks[1].id == "mid"
        assert worker.executed_tasks[2].id == "low"

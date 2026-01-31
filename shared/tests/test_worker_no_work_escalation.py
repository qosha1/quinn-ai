"""Tests for worker 'no work available' escalation logic.

Tests verify that workers escalate to their manager when they've been
idle without work for the configured threshold period.
"""

import time
from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from shared.wrkr.core.config import WorkerConfig
from shared.wrkr.core.result import WorkerResult
from shared.wrkr.core.task import Task
from shared.wrkr.core.worker import BaseWorker, EscalationResponse


class MockQueue:
    """Mock queue that can be configured to return None (no work)."""

    def __init__(self):
        self.tasks = []
        self.completed = []
        self.blocked = []

    def pop_highest_priority(self):
        if self.tasks:
            return self.tasks.pop(0)
        return None

    def push(self, task):
        self.tasks.append(task)

    def mark_done(self, task_id):
        self.completed.append(task_id)

    def mark_blocked(self, task_id, reason):
        self.blocked.append((task_id, reason))


class MockMemory:
    """Mock memory for recording task history."""

    def __init__(self):
        self.records = []

    def record(self, task, result):
        self.records.append((task, result))

    def recent(self, limit=10):
        return self.records[-limit:]


class MockEscalation:
    """Mock escalation interface that tracks escalation calls."""

    def __init__(self):
        self.reports = []
        self.asks = []

    def ask(self, issue, context):
        self.asks.append((issue, context))
        return EscalationResponse(resolved=False)

    def report(self, summary):
        self.reports.append(summary)

    def can_handle(self, issue):
        return True


class ConcreteTestWorker(BaseWorker):
    """Concrete test worker that just returns success."""

    def execute(self, task):
        return WorkerResult.success()


class TestWorkerNoWorkEscalation:
    """Tests for worker 'no work available' escalation."""

    @pytest.fixture
    def config(self):
        """Create worker config with short escalation threshold for testing."""
        return WorkerConfig(
            id="worker-1",
            name="Test Worker",
            boss_id="manager-1",
            idle_behavior="poll",
            poll_interval=0.01,  # 10ms poll for fast tests
            no_work_escalation_threshold_minutes=0.01,  # 0.6 seconds for fast tests
        )

    @pytest.fixture
    def queue(self):
        """Create empty queue (no work available)."""
        return MockQueue()

    @pytest.fixture
    def memory(self):
        """Create mock memory."""
        return MockMemory()

    @pytest.fixture
    def escalation(self):
        """Create mock escalation handler."""
        return MockEscalation()

    @pytest.fixture
    def worker(self, config, queue, memory, escalation):
        """Create test worker."""
        worker = ConcreteTestWorker(config, queue, memory, escalation)
        # Transition through proper state machine
        worker.transition_to(worker.state.__class__.ONBOARDING)
        worker.transition_to(worker.state.__class__.ACTIVE)
        return worker

    def test_no_escalation_when_work_available(
        self, worker, queue, escalation
    ):
        """Test no escalation when worker has work."""
        # Add work to queue
        task = Task(id="task-1", title="Test Task", description="Do something")
        queue.push(task)

        # Run one tick - should process task, not escalate
        worker._tick()

        # Verify no escalation
        assert len(escalation.reports) == 0
        assert len(escalation.asks) == 0

    def test_no_escalation_before_threshold(
        self, worker, queue, escalation
    ):
        """Test no escalation when idle but below threshold."""
        # Run a few ticks without work (but less than threshold)
        for _ in range(3):
            worker._tick()
            time.sleep(0.01)

        # Should have started tracking idle time
        assert worker._no_work_since is not None

        # But not escalated yet
        assert len(escalation.reports) == 0

    def test_escalation_after_threshold(
        self, worker, queue, escalation
    ):
        """Test escalation triggered after threshold exceeded."""
        # Run ticks for longer than threshold (0.6 seconds)
        start = time.monotonic()
        while time.monotonic() - start < 0.7:
            worker._tick()

        # Should have escalated
        assert len(escalation.reports) > 0
        assert "No work available" in escalation.reports[0]

    def test_escalation_only_once(
        self, worker, queue, escalation
    ):
        """Test escalation only happens once per idle period."""
        # Run ticks well beyond threshold
        start = time.monotonic()
        while time.monotonic() - start < 1.0:
            worker._tick()

        # Should have escalated exactly once
        assert len(escalation.reports) == 1

    def test_timer_reset_when_work_arrives(
        self, worker, queue, escalation
    ):
        """Test idle timer resets when work becomes available."""
        # Become idle for a bit
        for _ in range(5):
            worker._tick()
            time.sleep(0.01)

        assert worker._no_work_since is not None

        # Add work
        task = Task(id="task-1", title="Test Task", description="Do something")
        queue.push(task)

        # Process the task
        worker._tick()

        # Timer should be reset
        assert worker._no_work_since is None
        assert not worker._no_work_escalated

    def test_escalation_message_includes_duration(
        self, worker, queue, escalation
    ):
        """Test escalation message includes how long idle."""
        # Wait for escalation
        start = time.monotonic()
        while time.monotonic() - start < 0.7:
            worker._tick()

        # Check message format
        assert len(escalation.reports) > 0
        message = escalation.reports[0]
        assert "No work available" in message
        assert "minutes" in message

    def test_respects_config_threshold(self):
        """Test escalation respects configured threshold."""
        # Create worker with 2-minute threshold
        config = WorkerConfig(
            id="worker-1",
            name="Test Worker",
            boss_id="manager-1",
            idle_behavior="poll",
            poll_interval=0.01,
            no_work_escalation_threshold_minutes=2,  # 2 minutes
        )

        queue = MockQueue()
        memory = MockMemory()
        escalation = MockEscalation()

        worker = ConcreteTestWorker(config, queue, memory, escalation)
        worker.transition_to(worker.state.__class__.ONBOARDING)
        worker.transition_to(worker.state.__class__.ACTIVE)

        # Run for 1 second (way less than 2 minutes)
        start = time.monotonic()
        while time.monotonic() - start < 1.0:
            worker._tick()

        # Should NOT have escalated (threshold is 2 minutes)
        assert len(escalation.reports) == 0

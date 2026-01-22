"""Tests for the queue interface and MockQueue implementation.

Tests push, pop, priority ordering, and task state management.
"""

import pytest

from shared.wrkr.core.task import Task
from shared.queue.interface import MockQueue


class TestMockQueueCreation:
    """Tests for MockQueue initialization."""

    def test_empty_queue_creation(self) -> None:
        """MockQueue can be created empty."""
        queue = MockQueue()
        assert queue.size() == 0

    def test_empty_queue_collections(self) -> None:
        """MockQueue initializes with empty tracking collections."""
        queue = MockQueue()
        assert queue._tasks == []
        assert queue._in_progress == {}
        assert queue._done == {}
        assert queue._blocked == {}
        assert queue._failed == {}


class TestPushAndPop:
    """Tests for push() and pop_highest_priority() methods."""

    def test_push_single_task(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """push() adds a task to the queue."""
        mock_queue.push(sample_task)
        assert mock_queue.size() == 1

    def test_push_multiple_tasks(self, mock_queue: MockQueue) -> None:
        """push() can add multiple tasks."""
        for i in range(5):
            task = Task(id=f"task-{i}", title=f"Task {i}", description="Desc")
            mock_queue.push(task)
        assert mock_queue.size() == 5

    def test_pop_from_empty_queue(self, mock_queue: MockQueue) -> None:
        """pop_highest_priority() returns None for empty queue."""
        result = mock_queue.pop_highest_priority()
        assert result is None

    def test_pop_returns_task(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """pop_highest_priority() returns the task."""
        mock_queue.push(sample_task)
        result = mock_queue.pop_highest_priority()
        assert result == sample_task

    def test_pop_removes_task(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """pop_highest_priority() removes the task from queue."""
        mock_queue.push(sample_task)
        mock_queue.pop_highest_priority()
        assert mock_queue.size() == 0

    def test_pop_twice_returns_none(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """Second pop on single-task queue returns None."""
        mock_queue.push(sample_task)
        mock_queue.pop_highest_priority()
        result = mock_queue.pop_highest_priority()
        assert result is None

    def test_pop_tracks_in_progress(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """pop_highest_priority() tracks task as in-progress."""
        mock_queue.push(sample_task)
        mock_queue.pop_highest_priority()
        assert sample_task.id in mock_queue._in_progress


class TestPriorityOrdering:
    """Tests for priority-based ordering in the queue."""

    def test_highest_priority_first(self, mock_queue: MockQueue) -> None:
        """Lower priority number (higher priority) tasks are popped first."""
        low = Task(id="low", title="Low", description="Desc", priority=4)
        high = Task(id="high", title="High", description="Desc", priority=0)

        mock_queue.push(low)
        mock_queue.push(high)

        result = mock_queue.pop_highest_priority()
        assert result.id == "high"

    def test_priority_ordering_multiple(self, mock_queue: MockQueue) -> None:
        """Tasks are popped in priority order."""
        tasks = [
            Task(id="p4", title="P4", description="Desc", priority=4),
            Task(id="p2", title="P2", description="Desc", priority=2),
            Task(id="p0", title="P0", description="Desc", priority=0),
            Task(id="p3", title="P3", description="Desc", priority=3),
            Task(id="p1", title="P1", description="Desc", priority=1),
        ]

        for task in tasks:
            mock_queue.push(task)

        popped_ids = []
        while mock_queue.size() > 0:
            task = mock_queue.pop_highest_priority()
            popped_ids.append(task.id)

        assert popped_ids == ["p0", "p1", "p2", "p3", "p4"]

    def test_same_priority_ordering(self, mock_queue: MockQueue) -> None:
        """Tasks with same priority maintain insertion order."""
        task1 = Task(id="t1", title="T1", description="Desc", priority=2)
        task2 = Task(id="t2", title="T2", description="Desc", priority=2)
        task3 = Task(id="t3", title="T3", description="Desc", priority=2)

        mock_queue.push(task1)
        mock_queue.push(task2)
        mock_queue.push(task3)

        # Note: sort is stable, so insertion order is preserved for equal priorities
        popped = [mock_queue.pop_highest_priority().id for _ in range(3)]
        assert popped == ["t1", "t2", "t3"]


class TestPeek:
    """Tests for the peek() method."""

    def test_peek_empty_queue(self, mock_queue: MockQueue) -> None:
        """peek() returns empty list for empty queue."""
        result = mock_queue.peek()
        assert result == []

    def test_peek_returns_tasks(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """peek() returns tasks without removing them."""
        mock_queue.push(sample_task)
        result = mock_queue.peek()

        assert len(result) == 1
        assert result[0] == sample_task
        assert mock_queue.size() == 1  # Still in queue

    def test_peek_respects_limit(self, mock_queue: MockQueue) -> None:
        """peek() respects the limit parameter."""
        for i in range(10):
            mock_queue.push(Task(id=f"t{i}", title=f"T{i}", description="Desc"))

        result = mock_queue.peek(limit=3)
        assert len(result) == 3

    def test_peek_default_limit(self, mock_queue: MockQueue) -> None:
        """peek() has default limit of 10."""
        for i in range(15):
            mock_queue.push(Task(id=f"t{i}", title=f"T{i}", description="Desc"))

        result = mock_queue.peek()
        assert len(result) == 10

    def test_peek_returns_priority_ordered(self, mock_queue: MockQueue) -> None:
        """peek() returns tasks in priority order."""
        low = Task(id="low", title="Low", description="Desc", priority=4)
        high = Task(id="high", title="High", description="Desc", priority=0)

        mock_queue.push(low)
        mock_queue.push(high)

        result = mock_queue.peek()
        assert result[0].id == "high"
        assert result[1].id == "low"


class TestMarkDone:
    """Tests for the mark_done() method."""

    def test_mark_done_removes_from_queue(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """mark_done() removes task from active queue."""
        mock_queue.push(sample_task)
        mock_queue.mark_done(sample_task.id)

        assert mock_queue.size() == 0

    def test_mark_done_adds_to_done_dict(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """mark_done() records task in done collection."""
        mock_queue.push(sample_task)
        mock_queue.mark_done(sample_task.id)

        assert sample_task.id in mock_queue._done
        assert mock_queue._done[sample_task.id] == sample_task

    def test_mark_done_nonexistent_task(self, mock_queue: MockQueue) -> None:
        """mark_done() with nonexistent ID does nothing."""
        mock_queue.mark_done("nonexistent")
        assert mock_queue._done == {}

    def test_mark_done_correct_task(self, mock_queue: MockQueue) -> None:
        """mark_done() marks the correct task among multiple."""
        tasks = [
            Task(id=f"t{i}", title=f"T{i}", description="Desc")
            for i in range(3)
        ]
        for task in tasks:
            mock_queue.push(task)

        mock_queue.mark_done("t1")

        assert mock_queue.size() == 2
        assert "t1" in mock_queue._done


class TestMarkBlocked:
    """Tests for the mark_blocked() method."""

    def test_mark_blocked_removes_from_queue(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """mark_blocked() removes task from active queue."""
        mock_queue.push(sample_task)
        mock_queue.mark_blocked(sample_task.id, "Blocked by dependency")

        assert mock_queue.size() == 0

    def test_mark_blocked_adds_to_blocked_dict(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """mark_blocked() records task and reason in blocked collection."""
        mock_queue.push(sample_task)
        mock_queue.mark_blocked(sample_task.id, "Blocked by dependency")

        assert sample_task.id in mock_queue._blocked
        task, reason = mock_queue._blocked[sample_task.id]
        assert task == sample_task
        assert reason == "Blocked by dependency"

    def test_mark_blocked_nonexistent_task(self, mock_queue: MockQueue) -> None:
        """mark_blocked() with nonexistent ID does nothing."""
        mock_queue.mark_blocked("nonexistent", "reason")
        assert mock_queue._blocked == {}


class TestMarkFailed:
    """Tests for the mark_failed() method."""

    def test_mark_failed_removes_from_queue(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """mark_failed() removes task from active queue."""
        mock_queue.push(sample_task)
        mock_queue.mark_failed(sample_task.id, "Fatal error")

        assert mock_queue.size() == 0

    def test_mark_failed_adds_to_failed_dict(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """mark_failed() records task and error in failed collection."""
        mock_queue.push(sample_task)
        mock_queue.mark_failed(sample_task.id, "Fatal error")

        assert sample_task.id in mock_queue._failed
        task, error = mock_queue._failed[sample_task.id]
        assert task == sample_task
        assert error == "Fatal error"

    def test_mark_failed_nonexistent_task(self, mock_queue: MockQueue) -> None:
        """mark_failed() with nonexistent ID does nothing."""
        mock_queue.mark_failed("nonexistent", "error")
        assert mock_queue._failed == {}


class TestRequeue:
    """Tests for the requeue() method."""

    def test_requeue_blocked_task(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """requeue() returns blocked task to the queue."""
        mock_queue.push(sample_task)
        mock_queue.mark_blocked(sample_task.id, "temp block")

        assert mock_queue.size() == 0
        assert sample_task.id in mock_queue._blocked

        mock_queue.requeue(sample_task.id)

        assert mock_queue.size() == 1
        assert sample_task.id not in mock_queue._blocked

    def test_requeue_failed_task(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """requeue() returns failed task to the queue."""
        mock_queue.push(sample_task)
        mock_queue.mark_failed(sample_task.id, "temp error")

        assert mock_queue.size() == 0
        assert sample_task.id in mock_queue._failed

        mock_queue.requeue(sample_task.id)

        assert mock_queue.size() == 1
        assert sample_task.id not in mock_queue._failed

    def test_requeue_nonexistent_task(self, mock_queue: MockQueue) -> None:
        """requeue() with nonexistent ID does nothing."""
        mock_queue.requeue("nonexistent")
        assert mock_queue.size() == 0

    def test_requeue_restores_priority(self, mock_queue: MockQueue) -> None:
        """requeued task maintains its original priority."""
        high = Task(id="high", title="High", description="Desc", priority=0)
        low = Task(id="low", title="Low", description="Desc", priority=4)

        mock_queue.push(low)
        mock_queue.push(high)
        mock_queue.mark_blocked(high.id, "temp block")

        # Now only low is in queue
        assert mock_queue.size() == 1

        # Requeue high
        mock_queue.requeue(high.id)

        # High should be first again
        result = mock_queue.pop_highest_priority()
        assert result.id == "high"


class TestSize:
    """Tests for the size() method."""

    def test_size_empty(self, mock_queue: MockQueue) -> None:
        """size() returns 0 for empty queue."""
        assert mock_queue.size() == 0

    def test_size_after_push(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """size() increases after push."""
        mock_queue.push(sample_task)
        assert mock_queue.size() == 1

    def test_size_after_pop(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """size() decreases after pop."""
        mock_queue.push(sample_task)
        mock_queue.pop_highest_priority()
        assert mock_queue.size() == 0

    def test_size_excludes_done(self, mock_queue: MockQueue, sample_task: Task) -> None:
        """size() doesn't count done tasks."""
        mock_queue.push(sample_task)
        mock_queue.mark_done(sample_task.id)
        assert mock_queue.size() == 0

    def test_size_excludes_blocked(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """size() doesn't count blocked tasks."""
        mock_queue.push(sample_task)
        mock_queue.mark_blocked(sample_task.id, "blocked")
        assert mock_queue.size() == 0

    def test_size_excludes_failed(
        self, mock_queue: MockQueue, sample_task: Task
    ) -> None:
        """size() doesn't count failed tasks."""
        mock_queue.push(sample_task)
        mock_queue.mark_failed(sample_task.id, "failed")
        assert mock_queue.size() == 0


class TestQueueWithFixtures:
    """Tests using fixtures from conftest."""

    def test_mock_queue_fixture_is_empty(self, mock_queue: MockQueue) -> None:
        """mock_queue fixture provides empty queue."""
        assert mock_queue.size() == 0

    def test_mock_queue_with_tasks_fixture(
        self, mock_queue_with_tasks: MockQueue
    ) -> None:
        """mock_queue_with_tasks fixture has 3 tasks."""
        assert mock_queue_with_tasks.size() == 3

    def test_mock_queue_with_tasks_priority_order(
        self, mock_queue_with_tasks: MockQueue
    ) -> None:
        """mock_queue_with_tasks tasks are in priority order."""
        tasks = mock_queue_with_tasks.peek(limit=3)
        assert tasks[0].id == "task-high"  # priority 0
        assert tasks[1].id == "task-001"   # priority 2
        assert tasks[2].id == "task-low"   # priority 4

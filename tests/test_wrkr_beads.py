"""
Tests for wrkr beads integration.

Tests the BeadsQueue, BeadsMemory, and LinkManager classes
using in-memory implementations.
"""

import pytest
from datetime import datetime

from shared.wrkr.work.queue import InMemoryBeadsQueue
from shared.wrkr.work.memory import InMemoryBeadsMemory
from shared.wrkr.work.links import (
    Ask,
    InMemoryLinkManager,
    OKR,
    WorkLink,
)
from shared.wrkr.core.task import Task
from shared.wrkr.core.result import WorkerResult


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def worker_id():
    """Default worker ID for tests."""
    return "worker-1"


@pytest.fixture
def queue(worker_id):
    """Create an in-memory beads queue."""
    return InMemoryBeadsQueue(worker_id)


@pytest.fixture
def memory(worker_id):
    """Create an in-memory beads memory."""
    return InMemoryBeadsMemory(worker_id)


@pytest.fixture
def link_manager():
    """Create an in-memory link manager."""
    return InMemoryLinkManager()


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id="task-1",
        title="Implement feature X",
        description="Add the new feature X",
        priority=2,
    )


@pytest.fixture
def sample_result():
    """Create a sample successful result."""
    return WorkerResult.success(
        output="Feature X implemented successfully",
        duration_ms=1500,
    )


# =============================================================================
# InMemoryBeadsQueue Tests
# =============================================================================


class TestInMemoryBeadsQueue:
    """Tests for InMemoryBeadsQueue."""

    def test_empty_queue_returns_none(self, queue):
        task = queue.pop_highest_priority()
        assert task is None

    def test_add_and_pop_issue(self, queue):
        queue.add_issue(
            id="bd-001",
            title="Test task",
            description="Test description",
            priority=2,
        )

        task = queue.pop_highest_priority()
        assert task is not None
        assert task.id == "bd-001"
        assert task.title == "Test task"
        assert task.priority == 2

    def test_priority_ordering(self, queue):
        queue.add_issue(id="bd-low", title="Low priority", priority=4)
        queue.add_issue(id="bd-high", title="High priority", priority=0)
        queue.add_issue(id="bd-mid", title="Medium priority", priority=2)

        task1 = queue.pop_highest_priority()
        task2 = queue.pop_highest_priority()
        task3 = queue.pop_highest_priority()

        assert task1.id == "bd-high"
        assert task2.id == "bd-mid"
        assert task3.id == "bd-low"

    def test_blocked_tasks_skipped(self, queue):
        queue.add_issue(id="bd-blocked", title="Blocked task", blocked_by=["bd-other"])
        queue.add_issue(id="bd-ready", title="Ready task")

        task = queue.pop_highest_priority()
        assert task.id == "bd-ready"

    def test_mark_done(self, queue):
        queue.add_issue(id="bd-001", title="Task")
        task = queue.pop_highest_priority()

        queue.mark_done(task.id)

        # Issue should now be closed
        assert queue._issues["bd-001"]["status"] == "closed"

    def test_mark_blocked(self, queue):
        queue.add_issue(id="bd-001", title="Task")
        task = queue.pop_highest_priority()

        queue.mark_blocked(task.id, "Waiting for approval")

        assert queue._issues["bd-001"]["status"] == "blocked"
        assert queue._issues["bd-001"]["blocked_reason"] == "Waiting for approval"

    def test_mark_failed(self, queue):
        queue.add_issue(id="bd-001", title="Task")
        task = queue.pop_highest_priority()

        queue.mark_failed(task.id, "Connection timeout")

        assert queue._issues["bd-001"]["status"] == "closed"
        assert queue._issues["bd-001"]["failure_reason"] == "Connection timeout"

    def test_requeue(self, queue):
        queue.add_issue(id="bd-001", title="Task")
        task = queue.pop_highest_priority()
        queue.mark_blocked(task.id, "Waiting")

        queue.requeue(task.id)

        assert queue._issues["bd-001"]["status"] == "open"

    def test_peek(self, queue):
        queue.add_issue(id="bd-001", title="Task 1", priority=2)
        queue.add_issue(id="bd-002", title="Task 2", priority=1)

        tasks = queue.peek(limit=5)

        assert len(tasks) == 2
        assert tasks[0].id == "bd-002"  # Higher priority first
        # Tasks should still be in queue
        assert queue.size() == 2

    def test_size(self, queue):
        assert queue.size() == 0

        queue.add_issue(id="bd-001", title="Task 1")
        assert queue.size() == 1

        queue.add_issue(id="bd-002", title="Task 2")
        assert queue.size() == 2

        queue.pop_highest_priority()
        assert queue.size() == 1

    def test_push_task(self, queue, sample_task):
        queue.push(sample_task)

        task = queue.pop_highest_priority()
        assert task.id == sample_task.id
        assert task.title == sample_task.title

    def test_ask_okr_preserved(self, queue):
        queue.add_issue(
            id="bd-001",
            title="Task",
            ask_id="ask-123",
            okr_id="okr-456",
        )

        task = queue.pop_highest_priority()
        assert task.ask_id == "ask-123"
        assert task.okr_id == "okr-456"


# =============================================================================
# InMemoryBeadsMemory Tests
# =============================================================================


class TestInMemoryBeadsMemory:
    """Tests for InMemoryBeadsMemory."""

    def test_record_and_recent(self, memory, sample_task, sample_result):
        memory.record(sample_task, sample_result)

        records = memory.recent(limit=10)
        assert len(records) == 1
        assert records[0]["task_id"] == sample_task.id
        assert records[0]["result_succeeded"] is True

    def test_recent_order(self, memory):
        for i in range(5):
            task = Task(id=f"task-{i}", title=f"Task {i}", description="")
            result = WorkerResult.success(output=f"Output {i}")
            memory.record(task, result)

        records = memory.recent(limit=3)
        assert len(records) == 3
        # Most recent first
        assert records[0]["task_id"] == "task-4"
        assert records[1]["task_id"] == "task-3"
        assert records[2]["task_id"] == "task-2"

    def test_search(self, memory):
        memory.record(
            Task(id="t1", title="Implement login", description="Auth feature"),
            WorkerResult.success(output="Done"),
        )
        memory.record(
            Task(id="t2", title="Fix logout bug", description="Session issue"),
            WorkerResult.success(output="Done"),
        )
        memory.record(
            Task(id="t3", title="Add password reset", description="Auth feature"),
            WorkerResult.success(output="Done"),
        )

        results = memory.search("login", limit=5)
        assert len(results) == 1
        assert results[0]["task_id"] == "t1"

        results = memory.search("auth", limit=5)
        assert len(results) == 2  # Matches description

    def test_get_context_similar_tasks(self, memory):
        memory.record(
            Task(id="t1", title="Implement feature X", description=""),
            WorkerResult.success(output="Done"),
        )
        memory.record(
            Task(id="t2", title="Test feature Y", description=""),
            WorkerResult.success(output="Done"),
        )

        # Task with overlapping title words
        task = Task(id="t3", title="Implement feature Z", description="")
        context = memory.get_context(task)

        assert len(context["similar_tasks"]) >= 1
        assert any(r["task_id"] == "t1" for r in context["similar_tasks"])

    def test_get_context_escalation_guidance(self, memory):
        memory.record(
            Task(id="t1", title="API task", description=""),
            WorkerResult.escalate(
                reason="API credentials missing",
                output="Failed to authenticate",
            ),
        )

        task = Task(id="t2", title="Another API task", description="")
        context = memory.get_context(task)

        assert "guidance" in context
        assert "API credentials" in context["guidance"]

    def test_get_task_history(self, memory, sample_task, sample_result):
        memory.record(sample_task, sample_result)
        memory.record(sample_task, WorkerResult.failure(error="Retry failed"))

        history = memory.get_task_history(sample_task.id)
        assert len(history) == 2

    def test_success_rate(self, memory):
        for i in range(10):
            task = Task(id=f"t{i}", title=f"Task {i}", description="")
            if i < 7:
                result = WorkerResult.success(output="OK")
            else:
                result = WorkerResult.failure(error="Failed")
            memory.record(task, result)

        rate = memory.get_success_rate()
        assert rate == 0.7

    def test_success_rate_by_source(self, memory):
        # Queue tasks: 2 success, 1 failure
        for i in range(3):
            task = Task(id=f"q{i}", title="Queue task", description="", source="queue")
            result = WorkerResult.success(output="OK") if i < 2 else WorkerResult.failure(error="Fail")
            memory.record(task, result)

        # Beads tasks: 1 success, 1 failure
        for i in range(2):
            task = Task(id=f"b{i}", title="Beads task", description="", source="beads")
            result = WorkerResult.success(output="OK") if i == 0 else WorkerResult.failure(error="Fail")
            memory.record(task, result)

        queue_rate = memory.get_success_rate(task_source="queue")
        beads_rate = memory.get_success_rate(task_source="beads")

        assert queue_rate == pytest.approx(0.666, rel=0.01)
        assert beads_rate == 0.5


# =============================================================================
# InMemoryLinkManager Tests
# =============================================================================


class TestInMemoryLinkManager:
    """Tests for InMemoryLinkManager."""

    def test_add_and_get_ask(self, link_manager):
        ask = Ask(
            id="ask-001",
            title="Add dark mode support",
            requester="user@example.com",
        )
        link_manager.add_ask(ask)

        retrieved = link_manager.get_ask("ask-001")
        assert retrieved is not None
        assert retrieved.title == "Add dark mode support"
        assert retrieved.requester == "user@example.com"

    def test_add_and_get_okr(self, link_manager):
        okr = OKR(
            id="okr-001",
            objective="Improve user experience",
            key_results=["Reduce load time by 50%", "Increase retention by 20%"],
        )
        link_manager.add_okr(okr)

        retrieved = link_manager.get_okr("okr-001")
        assert retrieved is not None
        assert retrieved.objective == "Improve user experience"
        assert len(retrieved.key_results) == 2

    def test_link_task_to_ask(self, link_manager):
        ask = Ask(id="ask-001", title="Feature request")
        link_manager.add_ask(ask)

        link = link_manager.link_to_ask("task-001", "ask-001")

        assert link.link_type == "spawned-from"
        assert link.source_id == "task-001"
        assert link.target_id == "ask-001"

        # Ask should track spawned task
        updated_ask = link_manager.get_ask("ask-001")
        assert "task-001" in updated_ask.spawned_tasks

    def test_link_task_to_okr(self, link_manager):
        okr = OKR(id="okr-001", objective="Strategic goal")
        link_manager.add_okr(okr)

        link = link_manager.link_to_okr("task-001", "okr-001")

        assert link.link_type == "serves"
        assert link.source_id == "task-001"
        assert link.target_id == "okr-001"

        # OKR should track serving task
        updated_okr = link_manager.get_okr("okr-001")
        assert "task-001" in updated_okr.serving_tasks

    def test_get_task_ask(self, link_manager):
        ask = Ask(id="ask-001", title="Feature request")
        link_manager.add_ask(ask)
        link_manager.link_to_ask("task-001", "ask-001")

        retrieved_ask = link_manager.get_task_ask("task-001")
        assert retrieved_ask is not None
        assert retrieved_ask.id == "ask-001"

    def test_get_task_okr(self, link_manager):
        okr = OKR(id="okr-001", objective="Strategic goal")
        link_manager.add_okr(okr)
        link_manager.link_to_okr("task-001", "okr-001")

        retrieved_okr = link_manager.get_task_okr("task-001")
        assert retrieved_okr is not None
        assert retrieved_okr.id == "okr-001"

    def test_calculate_okr_progress(self, link_manager):
        okr = OKR(id="okr-001", objective="Complete project")
        link_manager.add_okr(okr)

        # Link 4 tasks
        for i in range(4):
            link_manager.link_to_okr(f"task-{i}", "okr-001")

        # Complete 2 of them
        link_manager.set_task_status("task-0", "closed")
        link_manager.set_task_status("task-1", "closed")
        link_manager.set_task_status("task-2", "open")
        link_manager.set_task_status("task-3", "in_progress")

        progress = link_manager.calculate_okr_progress("okr-001")
        assert progress == 0.5

    def test_update_okr_progress(self, link_manager):
        okr = OKR(id="okr-001", objective="Complete project", progress=0.0)
        link_manager.add_okr(okr)

        link_manager.link_to_okr("task-1", "okr-001")
        link_manager.link_to_okr("task-2", "okr-001")
        link_manager.set_task_status("task-1", "closed")

        new_progress = link_manager.update_okr_progress("okr-001")

        assert new_progress == 0.5
        assert link_manager.get_okr("okr-001").progress == 0.5

    def test_get_nonexistent_ask(self, link_manager):
        assert link_manager.get_ask("nonexistent") is None

    def test_get_nonexistent_okr(self, link_manager):
        assert link_manager.get_okr("nonexistent") is None

    def test_get_task_ask_when_not_linked(self, link_manager):
        assert link_manager.get_task_ask("task-no-link") is None

    def test_get_task_okr_when_not_linked(self, link_manager):
        assert link_manager.get_task_okr("task-no-link") is None


# =============================================================================
# WorkLink Tests
# =============================================================================


class TestWorkLink:
    """Tests for WorkLink dataclass."""

    def test_create_link(self):
        link = WorkLink(
            source_id="task-1",
            target_id="ask-1",
            link_type="spawned-from",
        )

        assert link.source_id == "task-1"
        assert link.target_id == "ask-1"
        assert link.link_type == "spawned-from"

    def test_to_dict(self):
        now = datetime.now()
        link = WorkLink(
            source_id="task-1",
            target_id="okr-1",
            link_type="serves",
            metadata={"priority": "high"},
            created_at=now,
        )

        d = link.to_dict()
        assert d["source_id"] == "task-1"
        assert d["target_id"] == "okr-1"
        assert d["link_type"] == "serves"
        assert d["metadata"]["priority"] == "high"
        assert d["created_at"] == now.isoformat()


# =============================================================================
# Integration Tests
# =============================================================================


class TestBeadsIntegration:
    """Integration tests for beads components working together."""

    def test_queue_memory_integration(self, queue, memory):
        """Test queue feeding tasks to worker with memory recording."""
        # Add tasks to queue
        queue.add_issue(id="bd-001", title="Task 1", priority=1)
        queue.add_issue(id="bd-002", title="Task 2", priority=2)

        # Process tasks
        while True:
            task = queue.pop_highest_priority()
            if task is None:
                break

            # Simulate execution
            result = WorkerResult.success(output=f"Completed {task.title}")
            memory.record(task, result)
            queue.mark_done(task.id)

        # Verify memory recorded both
        records = memory.recent(limit=10)
        assert len(records) == 2

    def test_ask_to_task_flow(self, queue, link_manager):
        """Test creating task from ask with proper linking."""
        # Create an ask
        ask = Ask(id="ask-feature", title="Add export feature", requester="pm@co.com")
        link_manager.add_ask(ask)

        # Create task from ask
        queue.add_issue(
            id="bd-task",
            title="Implement export",
            ask_id="ask-feature",
        )

        # Worker picks up task
        task = queue.pop_highest_priority()
        assert task.ask_id == "ask-feature"

        # Link task to ask
        link_manager.link_to_ask(task.id, task.ask_id)

        # Verify link
        retrieved_ask = link_manager.get_task_ask(task.id)
        assert retrieved_ask.title == "Add export feature"
        assert task.id in retrieved_ask.spawned_tasks

    def test_okr_progress_tracking(self, queue, link_manager):
        """Test OKR progress as tasks complete."""
        # Create OKR
        okr = OKR(id="okr-q1", objective="Ship v2.0")
        link_manager.add_okr(okr)

        # Create tasks serving OKR
        for i in range(4):
            queue.add_issue(
                id=f"bd-task-{i}",
                title=f"Task {i} for v2.0",
                okr_id="okr-q1",
            )

        # Link tasks to OKR and process some
        completed = 0
        while True:
            task = queue.pop_highest_priority()
            if task is None:
                break

            link_manager.link_to_okr(task.id, task.okr_id)

            # Complete first 3 tasks
            if completed < 3:
                queue.mark_done(task.id)
                link_manager.set_task_status(task.id, "closed")
                completed += 1
            else:
                queue.mark_blocked(task.id, "Waiting for review")
                link_manager.set_task_status(task.id, "blocked")

        # Check progress
        progress = link_manager.update_okr_progress("okr-q1")
        assert progress == 0.75  # 3 of 4 completed

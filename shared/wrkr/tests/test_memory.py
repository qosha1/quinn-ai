"""Tests for the memory interface and MockMemory implementation.

Tests record, recent, search, and get_context functionality.
"""

import pytest

from shared.wrkr.core.result import WorkerResult
from shared.wrkr.core.task import Task
from shared.wrkr.memory.interface import MockMemory


class TestMockMemoryCreation:
    """Tests for MockMemory initialization."""

    def test_empty_memory_creation(self) -> None:
        """MockMemory can be created empty."""
        memory = MockMemory()
        assert memory._records == []

    def test_empty_memory_recent(self) -> None:
        """Empty memory returns empty list for recent()."""
        memory = MockMemory()
        assert memory.recent() == []


class TestRecord:
    """Tests for the record() method."""

    def test_record_single_task(self, mock_memory: MockMemory, sample_task: Task) -> None:
        """record() stores a task execution."""
        result = WorkerResult.success("Completed")
        mock_memory.record(sample_task, result)

        records = mock_memory.recent()
        assert len(records) == 1

    def test_record_stores_task_fields(
        self, mock_memory: MockMemory, sample_task: Task
    ) -> None:
        """record() captures task fields correctly."""
        result = WorkerResult.success("Completed")
        mock_memory.record(sample_task, result)

        record = mock_memory.recent()[0]
        assert record["task_id"] == sample_task.id
        assert record["task_title"] == sample_task.title
        assert record["task_description"] == sample_task.description
        assert record["task_priority"] == sample_task.priority
        assert record["task_source"] == sample_task.source

    def test_record_stores_result_fields(
        self, mock_memory: MockMemory, sample_task: Task
    ) -> None:
        """record() captures result fields correctly."""
        result = WorkerResult.success(
            "Output text",
            duration_ms=150,
            artifacts=["/path/to/file.txt"],
            metadata={"key": "value"},
        )
        mock_memory.record(sample_task, result)

        record = mock_memory.recent()[0]
        assert record["result_succeeded"] is True
        assert record["result_output"] == "Output text"
        assert record["result_error"] is None
        assert record["result_duration_ms"] == 150
        assert record["result_artifacts"] == ["/path/to/file.txt"]
        assert record["result_metadata"] == {"key": "value"}

    def test_record_failure(self, mock_memory: MockMemory, sample_task: Task) -> None:
        """record() captures failure results correctly."""
        result = WorkerResult.failure("Something went wrong")
        mock_memory.record(sample_task, result)

        record = mock_memory.recent()[0]
        assert record["result_succeeded"] is False
        assert record["result_error"] == "Something went wrong"

    def test_record_escalation(self, mock_memory: MockMemory, sample_task: Task) -> None:
        """record() captures escalation results correctly."""
        result = WorkerResult.escalate("Need help")
        mock_memory.record(sample_task, result)

        record = mock_memory.recent()[0]
        assert record["result_needs_escalation"] is True
        assert record["result_escalation_reason"] == "Need help"

    def test_record_multiple_tasks(self, mock_memory: MockMemory) -> None:
        """record() can store multiple task executions."""
        for i in range(5):
            task = Task(id=f"task-{i}", title=f"Task {i}", description=f"Desc {i}")
            result = WorkerResult.success(f"Done {i}")
            mock_memory.record(task, result)

        records = mock_memory.recent(limit=10)
        assert len(records) == 5

    def test_record_with_metadata(
        self, mock_memory: MockMemory, task_with_metadata: Task
    ) -> None:
        """record() captures task metadata correctly."""
        result = WorkerResult.success("Done")
        mock_memory.record(task_with_metadata, result)

        record = mock_memory.recent()[0]
        assert record["task_metadata"] == task_with_metadata.metadata
        assert record["task_ask_id"] == "ask-123"
        assert record["task_okr_id"] == "okr-456"

    def test_record_created_at_as_isoformat(
        self, mock_memory: MockMemory, sample_task: Task
    ) -> None:
        """record() stores created_at as ISO format string."""
        result = WorkerResult.success("Done")
        mock_memory.record(sample_task, result)

        record = mock_memory.recent()[0]
        assert isinstance(record["task_created_at"], str)
        # ISO format should contain 'T' separator
        assert "T" in record["task_created_at"] or "-" in record["task_created_at"]


class TestRecent:
    """Tests for the recent() method."""

    def test_recent_empty(self, mock_memory: MockMemory) -> None:
        """recent() returns empty list when no records."""
        assert mock_memory.recent() == []

    def test_recent_default_limit(self, mock_memory: MockMemory) -> None:
        """recent() has default limit of 10."""
        for i in range(15):
            task = Task(id=f"task-{i}", title=f"Task {i}", description="Desc")
            mock_memory.record(task, WorkerResult.success("Done"))

        records = mock_memory.recent()
        assert len(records) == 10

    def test_recent_custom_limit(self, mock_memory: MockMemory) -> None:
        """recent() respects custom limit."""
        for i in range(10):
            task = Task(id=f"task-{i}", title=f"Task {i}", description="Desc")
            mock_memory.record(task, WorkerResult.success("Done"))

        records = mock_memory.recent(limit=3)
        assert len(records) == 3

    def test_recent_returns_reverse_chronological(
        self, mock_memory: MockMemory
    ) -> None:
        """recent() returns most recent first."""
        for i in range(5):
            task = Task(id=f"task-{i}", title=f"Task {i}", description="Desc")
            mock_memory.record(task, WorkerResult.success("Done"))

        records = mock_memory.recent()
        # Most recent (task-4) should be first
        assert records[0]["task_id"] == "task-4"
        assert records[-1]["task_id"] == "task-0"

    def test_recent_limit_larger_than_records(self, mock_memory: MockMemory) -> None:
        """recent() returns all records if limit > count."""
        for i in range(3):
            task = Task(id=f"task-{i}", title=f"Task {i}", description="Desc")
            mock_memory.record(task, WorkerResult.success("Done"))

        records = mock_memory.recent(limit=100)
        assert len(records) == 3


class TestSearch:
    """Tests for the search() method."""

    def test_search_empty_memory(self, mock_memory: MockMemory) -> None:
        """search() returns empty list on empty memory."""
        results = mock_memory.search("anything")
        assert results == []

    def test_search_title_match(self, mock_memory: MockMemory) -> None:
        """search() finds tasks by title substring."""
        task = Task(id="t1", title="Important Task", description="Some description")
        mock_memory.record(task, WorkerResult.success("Done"))

        results = mock_memory.search("Important")
        assert len(results) == 1
        assert results[0]["task_id"] == "t1"

    def test_search_description_match(self, mock_memory: MockMemory) -> None:
        """search() finds tasks by description substring."""
        task = Task(id="t1", title="Task", description="Contains special keyword here")
        mock_memory.record(task, WorkerResult.success("Done"))

        results = mock_memory.search("keyword")
        assert len(results) == 1
        assert results[0]["task_id"] == "t1"

    def test_search_case_insensitive(self, mock_memory: MockMemory) -> None:
        """search() is case-insensitive."""
        task = Task(id="t1", title="UPPERCASE Title", description="lowercase desc")
        mock_memory.record(task, WorkerResult.success("Done"))

        # Search with different case
        assert len(mock_memory.search("uppercase")) == 1
        assert len(mock_memory.search("LOWERCASE")) == 1
        assert len(mock_memory.search("Title")) == 1

    def test_search_no_match(self, mock_memory: MockMemory) -> None:
        """search() returns empty list when no match."""
        task = Task(id="t1", title="Task", description="Description")
        mock_memory.record(task, WorkerResult.success("Done"))

        results = mock_memory.search("nonexistent")
        assert results == []

    def test_search_default_limit(self, mock_memory: MockMemory) -> None:
        """search() has default limit of 5."""
        for i in range(10):
            task = Task(id=f"t{i}", title=f"Common Word {i}", description="Desc")
            mock_memory.record(task, WorkerResult.success("Done"))

        results = mock_memory.search("Common")
        assert len(results) == 5

    def test_search_custom_limit(self, mock_memory: MockMemory) -> None:
        """search() respects custom limit."""
        for i in range(10):
            task = Task(id=f"t{i}", title=f"Common Word {i}", description="Desc")
            mock_memory.record(task, WorkerResult.success("Done"))

        results = mock_memory.search("Common", limit=3)
        assert len(results) == 3

    def test_search_returns_most_recent_first(self, mock_memory: MockMemory) -> None:
        """search() returns matches in reverse chronological order."""
        for i in range(5):
            task = Task(id=f"t{i}", title=f"Task {i}", description="Common description")
            mock_memory.record(task, WorkerResult.success("Done"))

        results = mock_memory.search("Common")
        # Most recent should be first
        assert results[0]["task_id"] == "t4"


class TestGetContext:
    """Tests for the get_context() method."""

    def test_get_context_empty_memory(
        self, mock_memory: MockMemory, sample_task: Task
    ) -> None:
        """get_context() returns empty lists on empty memory."""
        context = mock_memory.get_context(sample_task)
        assert context["similar_tasks"] == []
        assert context["same_source"] == []

    def test_get_context_finds_same_source(self, mock_memory: MockMemory) -> None:
        """get_context() finds tasks from same source."""
        # Record a task from queue source
        task1 = Task(id="t1", title="Old Task", description="Desc", source="queue")
        mock_memory.record(task1, WorkerResult.success("Done"))

        # Get context for new queue task
        new_task = Task(id="new", title="New Task", description="Desc", source="queue")
        context = mock_memory.get_context(new_task)

        assert len(context["same_source"]) == 1
        assert context["same_source"][0]["task_id"] == "t1"

    def test_get_context_excludes_different_source(
        self, mock_memory: MockMemory
    ) -> None:
        """get_context() excludes tasks from different sources."""
        # Record a task from beads source
        task1 = Task(id="t1", title="Beads Task", description="Desc", source="beads")
        mock_memory.record(task1, WorkerResult.success("Done"))

        # Get context for queue task
        new_task = Task(id="new", title="Queue Task", description="Desc", source="queue")
        context = mock_memory.get_context(new_task)

        assert len(context["same_source"]) == 0

    def test_get_context_finds_similar_titles(self, mock_memory: MockMemory) -> None:
        """get_context() finds tasks with overlapping title words."""
        # Record a task with "Test" in title
        task1 = Task(id="t1", title="Test Task", description="Desc")
        mock_memory.record(task1, WorkerResult.success("Done"))

        # Get context for task with "Test" in title
        new_task = Task(id="new", title="Another Test", description="Desc")
        context = mock_memory.get_context(new_task)

        assert len(context["similar_tasks"]) == 1
        assert context["similar_tasks"][0]["task_id"] == "t1"

    def test_get_context_similar_titles_case_insensitive(
        self, mock_memory: MockMemory
    ) -> None:
        """get_context() title matching is case-insensitive."""
        task1 = Task(id="t1", title="TEST Task", description="Desc")
        mock_memory.record(task1, WorkerResult.success("Done"))

        new_task = Task(id="new", title="another test", description="Desc")
        context = mock_memory.get_context(new_task)

        assert len(context["similar_tasks"]) == 1

    def test_get_context_limits_results(self, mock_memory: MockMemory) -> None:
        """get_context() limits to 5 similar tasks and 5 same source."""
        # Record 10 tasks from same source with similar titles
        for i in range(10):
            task = Task(
                id=f"t{i}",
                title=f"Common Title {i}",
                description="Desc",
                source="queue",
            )
            mock_memory.record(task, WorkerResult.success("Done"))

        new_task = Task(id="new", title="Common Title", description="Desc", source="queue")
        context = mock_memory.get_context(new_task)

        # Should be limited to 5 each
        assert len(context["similar_tasks"]) <= 5
        assert len(context["same_source"]) <= 5

    def test_get_context_returns_most_recent(self, mock_memory: MockMemory) -> None:
        """get_context() returns most recent matching tasks."""
        for i in range(10):
            task = Task(
                id=f"t{i}",
                title=f"Common {i}",
                description="Desc",
                source="queue",
            )
            mock_memory.record(task, WorkerResult.success("Done"))

        new_task = Task(id="new", title="Common", description="Desc", source="queue")
        context = mock_memory.get_context(new_task)

        # Should include the most recent tasks (t5-t9)
        same_source_ids = [r["task_id"] for r in context["same_source"]]
        assert "t9" in same_source_ids
        assert "t8" in same_source_ids


class TestMemoryWithFixtures:
    """Tests using fixtures from conftest."""

    def test_mock_memory_fixture_is_empty(self, mock_memory: MockMemory) -> None:
        """mock_memory fixture provides empty memory."""
        assert mock_memory.recent() == []

    def test_mock_memory_with_records_fixture(
        self, mock_memory_with_records: MockMemory
    ) -> None:
        """mock_memory_with_records fixture has pre-recorded tasks."""
        records = mock_memory_with_records.recent()
        assert len(records) == 3

    def test_mock_memory_with_records_search(
        self, mock_memory_with_records: MockMemory
    ) -> None:
        """mock_memory_with_records can be searched."""
        results = mock_memory_with_records.search("Test")
        assert len(results) >= 1

    def test_mock_memory_with_records_has_failure(
        self, mock_memory_with_records: MockMemory
    ) -> None:
        """mock_memory_with_records includes a failed task."""
        results = mock_memory_with_records.search("Failed")
        assert len(results) == 1
        assert results[0]["result_succeeded"] is False

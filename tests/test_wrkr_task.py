"""Tests for the Task dataclass.

Tests task creation, default values, validation, and utility methods.
"""

from datetime import datetime

import pytest

from shared.wrkr.core.task import Task


class TestTaskCreation:
    """Tests for creating Task instances."""

    def test_minimal_creation(self) -> None:
        """Task can be created with only required fields."""
        task = Task(
            id="task-001",
            title="Test",
            description="A test task",
        )
        assert task.id == "task-001"
        assert task.title == "Test"
        assert task.description == "A test task"

    def test_default_priority(self) -> None:
        """Default priority is 2 (normal)."""
        task = Task(id="t1", title="Test", description="Desc")
        assert task.priority == 2

    def test_default_source(self) -> None:
        """Default source is 'queue'."""
        task = Task(id="t1", title="Test", description="Desc")
        assert task.source == "queue"

    def test_default_blocked_by(self) -> None:
        """Default blocked_by is an empty list."""
        task = Task(id="t1", title="Test", description="Desc")
        assert task.blocked_by == []
        assert isinstance(task.blocked_by, list)

    def test_default_metadata(self) -> None:
        """Default metadata is an empty dict."""
        task = Task(id="t1", title="Test", description="Desc")
        assert task.metadata == {}
        assert isinstance(task.metadata, dict)

    def test_created_at_default(self) -> None:
        """created_at defaults to approximately now."""
        before = datetime.now()
        task = Task(id="t1", title="Test", description="Desc")
        after = datetime.now()

        assert before <= task.created_at <= after

    def test_default_ask_id(self) -> None:
        """Default ask_id is None."""
        task = Task(id="t1", title="Test", description="Desc")
        assert task.ask_id is None

    def test_default_okr_id(self) -> None:
        """Default okr_id is None."""
        task = Task(id="t1", title="Test", description="Desc")
        assert task.okr_id is None

    def test_full_creation(self) -> None:
        """Task can be created with all fields specified."""
        created = datetime(2024, 1, 15, 10, 30, 0)
        task = Task(
            id="task-full",
            title="Full Task",
            description="A task with all fields",
            priority=1,
            source="beads",
            blocked_by=["dep-1", "dep-2"],
            metadata={"key": "value"},
            created_at=created,
            ask_id="ask-001",
            okr_id="okr-001",
        )

        assert task.id == "task-full"
        assert task.title == "Full Task"
        assert task.description == "A task with all fields"
        assert task.priority == 1
        assert task.source == "beads"
        assert task.blocked_by == ["dep-1", "dep-2"]
        assert task.metadata == {"key": "value"}
        assert task.created_at == created
        assert task.ask_id == "ask-001"
        assert task.okr_id == "okr-001"


class TestTaskPriorityValidation:
    """Tests for priority field validation."""

    def test_priority_0_valid(self) -> None:
        """Priority 0 (highest) is valid."""
        task = Task(id="t1", title="Test", description="Desc", priority=0)
        assert task.priority == 0

    def test_priority_1_valid(self) -> None:
        """Priority 1 is valid."""
        task = Task(id="t1", title="Test", description="Desc", priority=1)
        assert task.priority == 1

    def test_priority_2_valid(self) -> None:
        """Priority 2 (default) is valid."""
        task = Task(id="t1", title="Test", description="Desc", priority=2)
        assert task.priority == 2

    def test_priority_3_valid(self) -> None:
        """Priority 3 is valid."""
        task = Task(id="t1", title="Test", description="Desc", priority=3)
        assert task.priority == 3

    def test_priority_4_valid(self) -> None:
        """Priority 4 (lowest) is valid."""
        task = Task(id="t1", title="Test", description="Desc", priority=4)
        assert task.priority == 4

    def test_priority_negative_invalid(self) -> None:
        """Negative priority raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Task(id="t1", title="Test", description="Desc", priority=-1)
        assert "Priority must be between 0 and 4" in str(exc_info.value)

    def test_priority_5_invalid(self) -> None:
        """Priority 5 (above max) raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Task(id="t1", title="Test", description="Desc", priority=5)
        assert "Priority must be between 0 and 4" in str(exc_info.value)

    def test_priority_large_invalid(self) -> None:
        """Large priority value raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Task(id="t1", title="Test", description="Desc", priority=100)
        assert "Priority must be between 0 and 4" in str(exc_info.value)


class TestTaskSourceTypes:
    """Tests for all valid source types."""

    def test_source_queue(self) -> None:
        """Source 'queue' is valid."""
        task = Task(id="t1", title="Test", description="Desc", source="queue")
        assert task.source == "queue"

    def test_source_beads(self) -> None:
        """Source 'beads' is valid."""
        task = Task(id="t1", title="Test", description="Desc", source="beads")
        assert task.source == "beads"

    def test_source_escalation(self) -> None:
        """Source 'escalation' is valid."""
        task = Task(id="t1", title="Test", description="Desc", source="escalation")
        assert task.source == "escalation"

    def test_source_ask(self) -> None:
        """Source 'ask' is valid."""
        task = Task(id="t1", title="Test", description="Desc", source="ask")
        assert task.source == "ask"


class TestIsBlocked:
    """Tests for the is_blocked() method."""

    def test_is_blocked_empty(self) -> None:
        """Task with empty blocked_by is not blocked."""
        task = Task(id="t1", title="Test", description="Desc", blocked_by=[])
        assert task.is_blocked() is False

    def test_is_blocked_default(self) -> None:
        """Task with default blocked_by is not blocked."""
        task = Task(id="t1", title="Test", description="Desc")
        assert task.is_blocked() is False

    def test_is_blocked_one_dependency(self) -> None:
        """Task with one dependency is blocked."""
        task = Task(id="t1", title="Test", description="Desc", blocked_by=["dep-1"])
        assert task.is_blocked() is True

    def test_is_blocked_multiple_dependencies(self) -> None:
        """Task with multiple dependencies is blocked."""
        task = Task(
            id="t1",
            title="Test",
            description="Desc",
            blocked_by=["dep-1", "dep-2", "dep-3"],
        )
        assert task.is_blocked() is True


class TestTaskWithFixtures:
    """Tests using fixtures from conftest."""

    def test_sample_task_defaults(self, sample_task: Task) -> None:
        """Sample task has expected default values."""
        assert sample_task.priority == 2
        assert sample_task.source == "queue"
        assert not sample_task.is_blocked()

    def test_high_priority_task(self, high_priority_task: Task) -> None:
        """High priority task has priority 0."""
        assert high_priority_task.priority == 0
        assert high_priority_task.source == "escalation"

    def test_low_priority_task(self, low_priority_task: Task) -> None:
        """Low priority task has priority 4."""
        assert low_priority_task.priority == 4
        assert low_priority_task.source == "beads"

    def test_blocked_task(self, blocked_task: Task) -> None:
        """Blocked task fixture is blocked."""
        assert blocked_task.is_blocked()
        assert len(blocked_task.blocked_by) == 2

    def test_task_with_metadata(self, task_with_metadata: Task) -> None:
        """Task with metadata fixture has expected values."""
        assert task_with_metadata.metadata["key1"] == "value1"
        assert task_with_metadata.metadata["key2"] == 42
        assert task_with_metadata.metadata["nested"]["a"] == 1
        assert task_with_metadata.ask_id == "ask-123"
        assert task_with_metadata.okr_id == "okr-456"


class TestTaskMutability:
    """Tests for task field mutability."""

    def test_blocked_by_mutable(self) -> None:
        """blocked_by list can be modified after creation."""
        task = Task(id="t1", title="Test", description="Desc")
        assert not task.is_blocked()

        task.blocked_by.append("dep-1")
        assert task.is_blocked()

        task.blocked_by.clear()
        assert not task.is_blocked()

    def test_metadata_mutable(self) -> None:
        """metadata dict can be modified after creation."""
        task = Task(id="t1", title="Test", description="Desc")
        assert task.metadata == {}

        task.metadata["new_key"] = "new_value"
        assert task.metadata["new_key"] == "new_value"

    def test_separate_instances_have_separate_lists(self) -> None:
        """Each task instance has its own blocked_by list."""
        task1 = Task(id="t1", title="Test1", description="Desc")
        task2 = Task(id="t2", title="Test2", description="Desc")

        task1.blocked_by.append("dep-1")

        assert task1.is_blocked()
        assert not task2.is_blocked()

    def test_separate_instances_have_separate_dicts(self) -> None:
        """Each task instance has its own metadata dict."""
        task1 = Task(id="t1", title="Test1", description="Desc")
        task2 = Task(id="t2", title="Test2", description="Desc")

        task1.metadata["key"] = "value1"

        assert task1.metadata.get("key") == "value1"
        assert task2.metadata.get("key") is None

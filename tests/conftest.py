"""Shared pytest fixtures for wrkr module tests and integration tests.

Provides reusable fixtures for:
- Unit testing the worker system (MockQueue, MockMemory, etc.)
- Integration testing QuinnAI CLI via systemeval (temp orgs, qn runner)
"""

import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pytest

from shared.wrkr.core.config import WorkerConfig
from shared.wrkr.core.result import WorkerResult
from shared.wrkr.core.task import Task
from shared.escalation.interface import EscalationResponse, MockEscalation
from shared.wrkr.memory.interface import MockMemory
from shared.queue.interface import MockQueue


# =============================================================================
# INTEGRATION TEST FIXTURES (Systemeval)
# =============================================================================

def cleanup_org_sessions(org_path: Path) -> None:
    """Kill all tmux sessions associated with an org.

    Args:
        org_path: Path to org directory

    Returns:
        None
    """
    if not org_path.exists():
        return

    # Get worker IDs from database
    db_path = org_path / "live" / "quinn.db"
    if not db_path.exists():
        return

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT worker_id FROM workers")
        worker_ids = [row[0] for row in cursor.fetchall()]
        conn.close()
    except sqlite3.Error:
        # Database may not be initialized yet
        return

    # Kill tmux sessions for each worker
    for worker_id in worker_ids:
        session_name = f"quinn-{worker_id}"
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            check=False
        )


@pytest.fixture
def temp_org_factory():
    """Factory for creating isolated temp orgs with automatic cleanup.

    Yields:
        Callable that creates a new temp org directory

    Usage:
        def test_something(temp_org_factory):
            org1 = temp_org_factory("test_org_1")
            org2 = temp_org_factory("test_org_2")
            # Both orgs cleaned up automatically
    """
    orgs = []

    def _create_org(name: str = "test_org") -> Path:
        """Create a new temp org directory.

        Args:
            name: Optional name for the org (used in temp dir name)

        Returns:
            Path to created org directory
        """
        tmpdir = tempfile.mkdtemp(prefix=f"quinn_test_{name}_")
        org_path = Path(tmpdir)
        orgs.append(org_path)
        return org_path

    yield _create_org

    # Cleanup: kill sessions, remove dirs
    for org_path in orgs:
        cleanup_org_sessions(org_path)
        shutil.rmtree(org_path, ignore_errors=True)


@pytest.fixture
def qn_runner(temp_org_factory):
    """Wrapper for running qn commands via subprocess.

    Returns:
        Callable that runs qn command and returns CompletedProcess

    Usage:
        def test_something(qn_runner):
            result = qn_runner("org", "init", org_path=org)
            assert result.returncode == 0
    """
    def _run(*args: str, org_path: Path = None, env: dict = None, check: bool = True) -> subprocess.CompletedProcess:
        """Run qn command via subprocess.

        Args:
            *args: qn command arguments (e.g., "org", "init")
            org_path: Optional org path (adds --org-path if provided)
            env: Optional environment variables (merged with os.environ)
            check: If True, raise AssertionError on non-zero exit code

        Returns:
            subprocess.CompletedProcess with stdout, stderr, returncode

        Raises:
            AssertionError: If check=True and command fails
        """
        cmd = ["qn"]
        if org_path:
            cmd.extend(["--org-path", str(org_path)])
        cmd.extend(args)

        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=run_env,
            check=False
        )

        if check and result.returncode != 0:
            raise AssertionError(
                f"Command failed: {' '.join(cmd)}\n"
                f"Exit code: {result.returncode}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

        return result

    return _run


@pytest.fixture(autouse=True, scope="session")
def verify_no_leaked_sessions():
    """Ensure no quinn tmux sessions leak across test runs.

    This runs after all tests complete and fails if any quinn-* tmux
    sessions are still running.

    Raises:
        AssertionError: If quinn tmux sessions are detected after tests
    """
    yield

    result = subprocess.run(
        ["tmux", "list-sessions"],
        capture_output=True,
        text=True,
        check=False
    )

    # tmux list-sessions returns non-zero if no sessions exist
    if result.returncode != 0:
        return

    quinn_sessions = [
        line for line in result.stdout.splitlines()
        if "quinn-" in line
    ]

    if quinn_sessions:
        raise AssertionError(
            f"Leaked tmux sessions detected:\n" +
            "\n".join(quinn_sessions) +
            "\n\nTests must clean up all tmux sessions."
        )


# =============================================================================
# UNIT TEST FIXTURES (Worker Module)
# =============================================================================


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task for testing."""
    return Task(
        id="task-001",
        title="Test Task",
        description="A sample task for testing",
        priority=2,
        source="queue",
    )


@pytest.fixture
def high_priority_task() -> Task:
    """Create a high priority task (priority=0)."""
    return Task(
        id="task-high",
        title="Urgent Task",
        description="High priority urgent task",
        priority=0,
        source="escalation",
    )


@pytest.fixture
def low_priority_task() -> Task:
    """Create a low priority task (priority=4)."""
    return Task(
        id="task-low",
        title="Backlog Task",
        description="Low priority backlog task",
        priority=4,
        source="beads",
    )


@pytest.fixture
def blocked_task() -> Task:
    """Create a task that is blocked by dependencies."""
    return Task(
        id="task-blocked",
        title="Blocked Task",
        description="A task blocked by dependencies",
        priority=2,
        source="queue",
        blocked_by=["task-001", "task-002"],
    )


@pytest.fixture
def task_with_metadata() -> Task:
    """Create a task with metadata."""
    return Task(
        id="task-meta",
        title="Task with Metadata",
        description="A task containing metadata",
        priority=1,
        source="ask",
        metadata={"key1": "value1", "key2": 42, "nested": {"a": 1}},
        ask_id="ask-123",
        okr_id="okr-456",
    )


@pytest.fixture
def mock_queue() -> MockQueue:
    """Create an empty MockQueue."""
    return MockQueue()


@pytest.fixture
def mock_queue_with_tasks(sample_task: Task, high_priority_task: Task, low_priority_task: Task) -> MockQueue:
    """Create a MockQueue pre-populated with sample tasks."""
    queue = MockQueue()
    queue.push(sample_task)
    queue.push(high_priority_task)
    queue.push(low_priority_task)
    return queue


@pytest.fixture
def mock_memory() -> MockMemory:
    """Create an empty MockMemory."""
    return MockMemory()


@pytest.fixture
def mock_memory_with_records(sample_task: Task) -> MockMemory:
    """Create a MockMemory with some pre-recorded task executions."""
    memory = MockMemory()

    # Record a successful execution
    memory.record(
        sample_task,
        WorkerResult.success("Task completed successfully", duration_ms=100),
    )

    # Record a task with similar title
    similar_task = Task(
        id="task-similar",
        title="Test Task Variant",
        description="Another test task",
        priority=2,
        source="queue",
    )
    memory.record(
        similar_task,
        WorkerResult.success("Similar task completed", duration_ms=150),
    )

    # Record a failed task
    failed_task = Task(
        id="task-failed",
        title="Failed Task",
        description="A task that failed",
        priority=1,
        source="beads",
    )
    memory.record(
        failed_task,
        WorkerResult.failure("Something went wrong", duration_ms=50),
    )

    return memory


@pytest.fixture
def mock_escalation() -> MockEscalation:
    """Create a MockEscalation that resolves all issues."""
    return MockEscalation(resolve_issues=True)


@pytest.fixture
def mock_escalation_unresolved() -> MockEscalation:
    """Create a MockEscalation that never resolves issues."""
    return MockEscalation(resolve_issues=False)


@pytest.fixture
def sample_config() -> WorkerConfig:
    """Create a sample worker configuration."""
    return WorkerConfig(
        id="worker-001",
        name="Test Worker",
        skills={
            "coding": 80,
            "reasoning": 70,
            "research": 60,
            "management": 30,
            "strategy": 20,
            "creative": 50,
        },
        cost=50,
        role_id="developer",
        boss_id="manager-001",
        is_manager=False,
        idle_behavior="exit",
        poll_interval=1.0,
    )


@pytest.fixture
def manager_config() -> WorkerConfig:
    """Create a configuration for a manager worker."""
    return WorkerConfig(
        id="manager-001",
        name="Manager Worker",
        skills={
            "coding": 50,
            "reasoning": 80,
            "research": 70,
            "management": 90,
            "strategy": 75,
            "creative": 40,
        },
        cost=75,
        role_id="manager",
        boss_id=None,  # Reports to human
        is_manager=True,
        idle_behavior="poll",
        poll_interval=10.0,
    )


@pytest.fixture
def cheap_config() -> WorkerConfig:
    """Create a configuration for a cheap-tier worker."""
    return WorkerConfig(
        id="worker-cheap",
        name="Cheap Worker",
        skills={"coding": 30, "reasoning": 20},
        cost=15,
        role_id="assistant",
        boss_id="worker-001",
        idle_behavior="exit",
    )


@pytest.fixture
def top_config() -> WorkerConfig:
    """Create a configuration for a top-tier worker."""
    return WorkerConfig(
        id="worker-top",
        name="Top Worker",
        skills={
            "coding": 95,
            "reasoning": 95,
            "research": 90,
            "management": 85,
            "strategy": 90,
            "creative": 85,
        },
        cost=95,
        role_id="principal",
        boss_id=None,
        is_manager=True,
        idle_behavior="wait",
        poll_interval=30.0,
    )


@pytest.fixture
def success_result() -> WorkerResult:
    """Create a successful WorkerResult."""
    return WorkerResult.success(
        output="Task completed successfully",
        duration_ms=100,
        artifacts=["/path/to/artifact.txt"],
        metadata={"key": "value"},
    )


@pytest.fixture
def failure_result() -> WorkerResult:
    """Create a failed WorkerResult."""
    return WorkerResult.failure(
        error="Task failed due to error",
        duration_ms=50,
        metadata={"error_code": 500},
    )


@pytest.fixture
def escalation_result() -> WorkerResult:
    """Create a WorkerResult requiring escalation."""
    return WorkerResult.escalate(
        reason="Need manager approval",
        output="Partial progress made",
        duration_ms=200,
    )

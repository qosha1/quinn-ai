r"""BaseWorker: Pure state machine for worker lifecycle management.

This module implements the core worker abstraction as a state machine.
Workers have ZERO knowledge of providers (Claude, Codex, etc.) - the execute()
method is abstract and implementations live elsewhere.

The worker follows a simple lifecycle:
    PENDING -> ONBOARDING -> ACTIVE <-> WORKING -> OFFBOARDING -> TERMINATED
                                    \-> STUCK -/
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from shared.wrkr.core.config import WorkerConfig
from shared.wrkr.core.result import WorkerResult
from shared.wrkr.core.state import InvalidTransition, WorkerState, transition
from shared.wrkr.core.task import Task


# =============================================================================
# Protocol Interfaces
# =============================================================================


class QueueInterface(Protocol):
    """Protocol for task queue operations."""

    def pop_highest_priority(self) -> Task | None:
        """Remove and return the highest priority task, or None if empty."""
        ...

    def push(self, task: Task) -> None:
        """Add a task to the queue."""
        ...

    def mark_done(self, task_id: str) -> None:
        """Mark a task as completed."""
        ...

    def mark_blocked(self, task_id: str, reason: str) -> None:
        """Mark a task as blocked with a reason."""
        ...


class MemoryInterface(Protocol):
    """Protocol for worker memory/history operations."""

    def record(self, task: Task, result: WorkerResult) -> None:
        """Record a task execution in memory."""
        ...

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve recent task executions."""
        ...


class EscalationInterface(Protocol):
    """Protocol for escalation operations to manager/human."""

    def ask(self, issue: str, context: dict[str, Any]) -> EscalationResponse:
        """Ask for help with an issue."""
        ...

    def report(self, summary: str) -> None:
        """Report a summary to manager."""
        ...


@dataclass
class EscalationResponse:
    """Response from an escalation request.

    Attributes:
        resolved: Whether the escalation was resolved.
        guidance: Guidance provided by the escalation handler.
        new_tasks: New tasks spawned as a result of escalation.
    """

    resolved: bool
    guidance: str = ""
    new_tasks: list[Task] = field(default_factory=list)


# =============================================================================
# BaseWorker
# =============================================================================


class BaseWorker(ABC):
    """Pure state machine base class for workers.

    Workers are the fundamental execution units in the QuinnAI system.
    They process tasks from a queue, record results to memory, and
    escalate issues when stuck.

    IMPORTANT: This class has ZERO knowledge of providers (Claude, Codex, etc).
    The execute() method is abstract - concrete implementations live in
    provider-specific subclasses.

    Lifecycle:
        1. Worker starts in PENDING state
        2. run() transitions to ONBOARDING, calls _onboard()
        3. Transitions to ACTIVE, enters main tick loop
        4. Each tick: pop task -> WORKING -> execute -> record -> ACTIVE
        5. If stuck, transitions to STUCK and escalates
        6. stop() signals graceful shutdown via OFFBOARDING
        7. Finally transitions to TERMINATED

    Attributes:
        config: Worker configuration (identity, skills, hierarchy).
        queue: Task queue interface.
        memory: Memory/history interface.
        escalation: Escalation interface.
    """

    def __init__(
        self,
        config: WorkerConfig,
        queue: QueueInterface,
        memory: MemoryInterface,
        escalation: EscalationInterface,
    ) -> None:
        """Initialize the worker.

        Args:
            config: Worker configuration defining identity and capabilities.
            queue: Interface for task queue operations.
            memory: Interface for recording task history.
            escalation: Interface for escalating issues.
        """
        self._config = config
        self._queue = queue
        self._memory = memory
        self._escalation = escalation
        self._state = WorkerState.PENDING
        self._should_stop = False

    @property
    def config(self) -> WorkerConfig:
        """Worker configuration."""
        return self._config

    @property
    def state(self) -> WorkerState:
        """Current worker state."""
        return self._state

    def transition_to(self, new_state: WorkerState) -> None:
        """Transition to a new state.

        Validates the transition is allowed and updates internal state.
        Calls _on_state_change() hook after successful transition.

        Args:
            new_state: The target state to transition to.

        Raises:
            InvalidTransition: If the transition is not allowed.
        """
        self._state = transition(self._state, new_state)
        self._on_state_change(new_state)

    def run(self) -> None:
        """Main worker loop.

        Executes the full worker lifecycle:
            1. Transition to ONBOARDING, call _onboard()
            2. Transition to ACTIVE
            3. Tick loop until stop signal or termination
            4. Transition through OFFBOARDING to TERMINATED
        """
        try:
            # Onboarding phase
            self.transition_to(WorkerState.ONBOARDING)
            self._onboard()

            # Enter active state
            self.transition_to(WorkerState.ACTIVE)

            # Main tick loop
            while not self._should_stop and self._state not in (
                WorkerState.OFFBOARDING,
                WorkerState.TERMINATED,
            ):
                self._tick()

            # Graceful shutdown
            if self._state == WorkerState.OFFBOARDING:
                self.transition_to(WorkerState.TERMINATED)
            elif self._state not in (WorkerState.TERMINATED,):
                self.transition_to(WorkerState.OFFBOARDING)
                self.transition_to(WorkerState.TERMINATED)

        except InvalidTransition:
            # If we can't transition cleanly, force to terminated if possible
            if self._state != WorkerState.TERMINATED:
                try:
                    self.transition_to(WorkerState.OFFBOARDING)
                    self.transition_to(WorkerState.TERMINATED)
                except InvalidTransition:
                    # Already in a terminal path, let it be
                    pass
            raise

    def stop(self) -> None:
        """Signal graceful shutdown.

        Sets the stop flag and transitions to OFFBOARDING state.
        The main loop will complete its current operation and then
        transition to TERMINATED.
        """
        self._should_stop = True
        if self._state in (WorkerState.ACTIVE, WorkerState.WORKING, WorkerState.STUCK):
            self.transition_to(WorkerState.OFFBOARDING)

    def _tick(self) -> None:
        """Execute one iteration of the work loop.

        Pops the highest priority task from the queue and processes it.
        If no task is available, handles idle state based on config.
        """
        task = self._queue.pop_highest_priority()

        if task is None:
            self._idle()
            return

        self._handle_task(task)

    def _handle_task(self, task: Task) -> None:
        """Execute a task and process its result.

        Transitions to WORKING state, executes the task, records the
        result, and handles any escalation needs.

        Args:
            task: The task to execute.
        """
        # Transition to working state
        self.transition_to(WorkerState.WORKING)

        # Execute the task
        start_time = time.monotonic()
        try:
            result = self.execute(task)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            if result.duration_ms is None:
                result.duration_ms = duration_ms
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            result = WorkerResult.failure(
                error=str(e),
                duration_ms=duration_ms,
                metadata={"exception_type": type(e).__name__},
            )

        # Record and handle result
        self._memory.record(task, result)
        self._handle_result(task, result)

    def _handle_result(self, task: Task, result: WorkerResult) -> None:
        """Process a task result.

        Marks the task as done or blocked, handles escalation if needed,
        and transitions back to ACTIVE state.

        Args:
            task: The task that was executed.
            result: The result of the execution.
        """
        if result.succeeded:
            self._queue.mark_done(task.id)
            self.transition_to(WorkerState.ACTIVE)

        elif result.needs_escalation:
            # Transition to stuck and escalate
            self.transition_to(WorkerState.STUCK)

            response = self.escalate(result.escalation_reason)

            if response.resolved:
                # Push any new tasks from escalation
                for new_task in response.new_tasks:
                    self._queue.push(new_task)
                self._queue.mark_done(task.id)
                self.transition_to(WorkerState.ACTIVE)
            else:
                # Mark as blocked and continue
                self._queue.mark_blocked(task.id, result.escalation_reason)
                self.transition_to(WorkerState.ACTIVE)

        else:
            # Failed but doesn't need escalation - mark blocked and continue
            self._queue.mark_blocked(task.id, result.error or "Unknown error")
            self.transition_to(WorkerState.ACTIVE)

    def _idle(self) -> None:
        """Handle idle state when no tasks are available.

        Behavior is determined by config.idle_behavior:
            - "wait": Block indefinitely (sleep with poll interval)
            - "poll": Sleep for poll_interval then check again
            - "exit": Signal shutdown
        """
        behavior = self._config.idle_behavior

        if behavior == "exit":
            self.stop()
        elif behavior in ("wait", "poll"):
            time.sleep(self._config.poll_interval)

    def _onboard(self) -> None:
        """Initialization hook called during ONBOARDING state.

        Override this method to perform any setup required before
        the worker becomes active. Default implementation does nothing.
        """
        pass

    def _on_state_change(self, new_state: WorkerState) -> None:
        """Hook called after every state change.

        Override this method to perform actions on state transitions,
        such as logging, metrics, or notifications.

        Args:
            new_state: The state that was just entered.
        """
        pass

    @abstractmethod
    def execute(self, task: Task) -> WorkerResult:
        """Execute a task and return the result.

        This is the core work method that subclasses must implement.
        The implementation should have ZERO knowledge of this base class's
        state machine - it simply receives a task and returns a result.

        Args:
            task: The task to execute.

        Returns:
            The result of the task execution.
        """
        ...

    def escalate(self, issue: str) -> EscalationResponse:
        """Escalate an issue to the manager/human.

        Args:
            issue: Description of the issue requiring escalation.

        Returns:
            The response from the escalation handler.
        """
        context = {
            "worker_id": self._config.id,
            "worker_name": self._config.name,
            "state": self._state.value,
            "recent_history": self._memory.recent(limit=5),
        }
        return self._escalation.ask(issue, context)

"""
SessionWorker: Worker implementation that uses pyterm sessions for execution.

This module bridges the provider-agnostic wrkr state machine to actual
AI execution via pyterm's AgentSession. The worker owns its session
(1:1 relationship) and manages its lifecycle.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from shared.wrkr.core.config import WorkerConfig
from shared.wrkr.core.result import WorkerResult
from shared.wrkr.core.state import WorkerState
from shared.wrkr.core.task import Task
from shared.wrkr.core.worker import BaseWorker
from shared.wrkr.session.adapter import (
    DefaultPromptBuilder,
    PromptBuilder,
    ResultExtractor,
)


class SessionFactory(Protocol):
    """Protocol for creating sessions from worker config."""

    def __call__(self, config: WorkerConfig) -> Any:
        """Create a session for the given worker config."""
        ...


class SessionWorker(BaseWorker):
    """
    Worker that executes tasks through AI sessions.

    SessionWorker extends BaseWorker to implement execute() using pyterm
    AgentSession. The session lifecycle is tied to the worker lifecycle:
    - Session created during ONBOARDING
    - Session used for execute() calls
    - Session destroyed during OFFBOARDING

    The worker remains provider-agnostic - the session_factory determines
    which AI provider is used based on worker config (skills/cost).

    Example:
        def create_session(config: WorkerConfig) -> AgentSession:
            return AgentSession.create(
                worker_id=config.id,
                provider="claude_code",
            )

        worker = SessionWorker(
            config=config,
            queue=queue,
            memory=memory,
            escalation=escalation,
            session_factory=create_session,
        )
        worker.run()
    """

    def __init__(
        self,
        config: WorkerConfig,
        queue: Any,  # QueueInterface
        memory: Any,  # MemoryInterface
        escalation: Any,  # EscalationInterface
        session_factory: SessionFactory,
        prompt_builder: PromptBuilder | None = None,
        result_extractor: ResultExtractor | None = None,
        default_timeout: float | None = None,
    ) -> None:
        """
        Initialize the session worker.

        Args:
            config: Worker configuration (id, name, skills, cost, etc.)
            queue: Task queue interface
            memory: Memory interface for history
            escalation: Escalation interface for help requests
            session_factory: Factory function to create sessions
            prompt_builder: Optional custom prompt builder
            result_extractor: Optional custom result extractor
            default_timeout: Default timeout for prompt execution (seconds)
        """
        super().__init__(config, queue, memory, escalation)
        self._session_factory = session_factory
        self._session: Any = None  # AgentSession, set during onboarding
        self._prompt_builder = prompt_builder or DefaultPromptBuilder()
        self._result_extractor = result_extractor or ResultExtractor()
        self._default_timeout = default_timeout

    @property
    def session(self) -> Any:
        """Get the current session (None if not onboarded)."""
        return self._session

    @property
    def has_session(self) -> bool:
        """Check if worker has an active session."""
        return self._session is not None

    def _onboard(self) -> None:
        """
        Create and start the session during onboarding.

        Called automatically when worker transitions to ONBOARDING state.
        Creates a session using the factory and starts it.
        """
        # Create session using factory
        self._session = self._session_factory(self._config)

        # Start the session
        self._session.start()

        # Wait for session to be ready (idle state)
        if hasattr(self._session, "wait_for_idle"):
            self._session.wait_for_idle(timeout=30.0)

    def _on_state_change(self, new_state: WorkerState) -> None:
        """
        Handle state changes, particularly for session cleanup.

        Args:
            new_state: The state being entered
        """
        # Clean up session when entering TERMINATED
        if new_state == WorkerState.TERMINATED and self._session is not None:
            self._cleanup_session()

    def _cleanup_session(self) -> None:
        """Stop and clean up the session."""
        if self._session is not None:
            try:
                self._session.stop()
            except Exception:
                # Force stop on error
                try:
                    self._session.stop(force=True)
                except Exception:
                    pass  # Best effort cleanup
            finally:
                self._session = None

    def execute(self, task: Task) -> WorkerResult:
        """
        Execute a task using the AI session.

        Converts the task to a prompt, sends it to the session,
        and converts the response to a WorkerResult.

        Args:
            task: The task to execute

        Returns:
            WorkerResult indicating success, failure, or escalation need
        """
        if not self.has_session:
            return WorkerResult.failure(
                error="No active session - worker not properly onboarded",
                metadata={"task_id": task.id},
            )

        # Get context from memory for better prompts
        context = None
        if hasattr(self._memory, "get_context"):
            try:
                context = self._memory.get_context(task)
            except Exception:
                pass  # Context is optional

        # Build prompt from task
        prompt = self._prompt_builder.build(task, context)

        # Execute via session
        try:
            result = self._session.send_prompt(
                prompt,
                timeout=self._default_timeout,
                task_id=task.id,
                task_title=task.title,
            )
        except TimeoutError:
            return WorkerResult.escalate(
                reason=f"Task execution timed out after {self._default_timeout}s",
                metadata={"task_id": task.id, "timeout": self._default_timeout},
            )
        except Exception as e:
            return WorkerResult.failure(
                error=f"Session error: {str(e)}",
                metadata={"task_id": task.id, "exception": type(e).__name__},
            )

        # Convert response to WorkerResult
        return self._result_extractor.extract(result, task)


class TimeoutError(Exception):
    """Raised when session execution times out."""

    pass


def create_session_worker(
    config: WorkerConfig,
    queue: Any,
    memory: Any,
    escalation: Any,
    session_factory: SessionFactory,
    **kwargs,
) -> SessionWorker:
    """
    Factory function to create a SessionWorker.

    Args:
        config: Worker configuration
        queue: Task queue
        memory: Memory interface
        escalation: Escalation interface
        session_factory: Session creation function
        **kwargs: Additional arguments for SessionWorker

    Returns:
        Configured SessionWorker instance
    """
    return SessionWorker(
        config=config,
        queue=queue,
        memory=memory,
        escalation=escalation,
        session_factory=session_factory,
        **kwargs,
    )

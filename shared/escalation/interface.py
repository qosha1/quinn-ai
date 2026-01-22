"""
Escalation interface definitions for worker-to-supervisor communication.

This module defines the protocol for workers to escalate issues to supervisors
or external systems when they encounter problems they cannot resolve independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

# Import Task only for type checking to avoid circular imports with shared.wrkr
if TYPE_CHECKING:
    from shared.wrkr.core.task import Task


@dataclass
class EscalationResponse:
    """
    Response from an escalation request.

    Attributes:
        resolved: Whether the issue was successfully resolved by the escalation
            handler. If True, the worker can proceed with the provided guidance.
            If False, the issue remains unresolved.
        guidance: Instructions or information provided by the escalation handler
            to help resolve the issue. Empty string if no guidance available.
        new_tasks: Additional tasks created as a result of the escalation.
            These should be added to the worker's queue for processing.
        escalated_to: Identifier of who/what handled the escalation, if known.
            Could be a supervisor worker ID, system name, or None if unhandled.
    """

    resolved: bool
    guidance: str = ""
    new_tasks: list["Task"] = field(default_factory=list)
    escalated_to: str | None = None


class EscalationInterface(Protocol):
    """
    Protocol defining the escalation interface for workers.

    Workers use this interface to escalate issues they cannot handle,
    report progress or completion to supervisors, and check whether
    an issue can be handled through escalation.

    Implementations may route to supervisors, external systems, human
    operators, or simply log and reject escalations.
    """

    def ask(self, issue: str, context: dict[str, Any]) -> EscalationResponse:
        """
        Escalate an issue for resolution.

        Args:
            issue: Description of the problem or question that needs resolution.
            context: Additional contextual information about the issue, such as
                current task state, attempted solutions, or relevant data.

        Returns:
            EscalationResponse containing resolution status and any guidance.
        """
        ...

    def report(self, summary: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Report progress or completion to the escalation handler.

        Used to keep supervisors informed of work status without requesting
        assistance. Reports are informational and do not expect a response.

        Args:
            summary: Brief description of what is being reported.
            metadata: Optional additional data about the report, such as
                metrics, timestamps, or task identifiers.
        """
        ...

    def can_handle(self, issue: str) -> bool:
        """
        Check if this escalation handler can potentially handle an issue.

        Allows workers to check availability before attempting escalation.
        This is a lightweight check and does not guarantee resolution.

        Args:
            issue: Description of the problem to check.

        Returns:
            True if the handler may be able to help with this issue,
            False if escalation would definitely fail.
        """
        ...


class MockEscalation:
    """
    Mock escalation handler for testing purposes.

    Provides configurable behavior and tracks all interactions for
    test assertions. By default, resolves all issues.

    Attributes:
        resolve_issues: Whether to resolve escalated issues. Default True.
        default_guidance: Guidance string to return when resolving.
        escalated_to_name: Name to report as the handler.
        asks: List of all (issue, context) tuples from ask() calls.
        reports: List of all (summary, metadata) tuples from report() calls.
        can_handle_checks: List of all issues passed to can_handle().
    """

    def __init__(
        self,
        resolve_issues: bool = True,
        default_guidance: str = "Mock guidance provided.",
        escalated_to_name: str = "mock_handler",
    ) -> None:
        """
        Initialize the mock escalation handler.

        Args:
            resolve_issues: Whether ask() should return resolved=True.
            default_guidance: Guidance string to include in responses.
            escalated_to_name: Name to use for escalated_to field.
        """
        self.resolve_issues = resolve_issues
        self.default_guidance = default_guidance
        self.escalated_to_name = escalated_to_name
        self.asks: list[tuple[str, dict[str, Any]]] = []
        self.reports: list[tuple[str, dict[str, Any] | None]] = []
        self.can_handle_checks: list[str] = []

    def ask(self, issue: str, context: dict[str, Any]) -> EscalationResponse:
        """
        Record the ask and return a configurable response.

        Args:
            issue: Description of the problem.
            context: Additional contextual information.

        Returns:
            EscalationResponse based on configured resolve_issues setting.
        """
        self.asks.append((issue, context))
        return EscalationResponse(
            resolved=self.resolve_issues,
            guidance=self.default_guidance if self.resolve_issues else "",
            new_tasks=[],
            escalated_to=self.escalated_to_name if self.resolve_issues else None,
        )

    def report(self, summary: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Record the report for later assertion.

        Args:
            summary: Brief description of what is being reported.
            metadata: Optional additional data about the report.
        """
        self.reports.append((summary, metadata))

    def can_handle(self, issue: str) -> bool:
        """
        Record the check and return based on resolve_issues setting.

        Args:
            issue: Description of the problem to check.

        Returns:
            Value of resolve_issues configuration.
        """
        self.can_handle_checks.append(issue)
        return self.resolve_issues

    def reset(self) -> None:
        """Clear all recorded interactions for fresh test assertions."""
        self.asks.clear()
        self.reports.clear()
        self.can_handle_checks.clear()


class NoopEscalation:
    """
    No-operation escalation handler for workers without an escalation path.

    All escalation attempts return unresolved. Reports are silently ignored.
    Use this for leaf workers or when escalation is intentionally disabled.
    """

    def ask(self, issue: str, context: dict[str, Any]) -> EscalationResponse:
        """
        Return an unresolved response for any issue.

        Args:
            issue: Description of the problem (ignored).
            context: Additional contextual information (ignored).

        Returns:
            EscalationResponse with resolved=False and empty fields.
        """
        return EscalationResponse(
            resolved=False,
            guidance="",
            new_tasks=[],
            escalated_to=None,
        )

    def report(self, summary: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Silently ignore the report.

        Args:
            summary: Brief description of what is being reported (ignored).
            metadata: Optional additional data (ignored).
        """
        pass

    def can_handle(self, issue: str) -> bool:
        """
        Always return False - this handler cannot handle anything.

        Args:
            issue: Description of the problem (ignored).

        Returns:
            Always False.
        """
        return False

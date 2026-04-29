"""
Business logic exceptions for QuinnAI.

These exceptions represent invalid operations or states in the
business logic layer, independent of storage implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class InvalidStateTransition(Exception):
    """Raised when attempting an invalid state transition.

    Used for both worker lifecycle/runtime and org lifecycle transitions.
    """

    def __init__(self, current: str, attempted: str, valid: list[str]):
        self.current = current
        self.attempted = attempted
        self.valid = valid
        super().__init__(
            f"Cannot transition from '{current}' to '{attempted}'. "
            f"Valid transitions: {valid}"
        )


class WorkerNotFound(Exception):
    """Raised when worker doesn't exist."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        super().__init__(f"Worker not found: {worker_id}")


class InvalidLifecycleState(Exception):
    """Raised when operation not allowed in current lifecycle state."""

    def __init__(self, operation: str, lifecycle: str):
        self.operation = operation
        self.lifecycle = lifecycle
        super().__init__(
            f"Cannot {operation} when lifecycle is '{lifecycle}'"
        )


class InvalidOrgTransition(Exception):
    """Raised when attempting an invalid org state transition."""

    def __init__(self, current: str, attempted: str, valid: list[str]):
        self.current = current
        self.attempted = attempted
        self.valid = valid
        super().__init__(
            f"Cannot transition org from '{current}' to '{attempted}'. "
            f"Valid transitions: {valid}"
        )


class OrgNotInitialized(Exception):
    """Raised when operation requires initialized org."""

    def __init__(self, operation: str):
        self.operation = operation
        super().__init__(f"Cannot {operation}: org is not initialized")


class ActiveSessionExistsError(Exception):
    """Raised when trying to spawn a session for a worker that already has one.

    This enforces the 1:1 relationship between workers and sessions.
    """

    def __init__(self, worker_id: str, existing_session_id: str):
        self.worker_id = worker_id
        self.existing_session_id = existing_session_id
        super().__init__(
            f"Worker '{worker_id}' already has an active session: {existing_session_id}"
        )


class ConfigurationError(Exception):
    """Raised when provider or org configuration is invalid.

    Used at startup to detect configuration problems early rather than
    failing at runtime when a provider is first used.
    """

    def __init__(self, message: str, provider: str | None = None, field: str | None = None):
        self.provider = provider
        self.field = field
        if provider and field:
            full_message = f"Configuration error for provider '{provider}', field '{field}': {message}"
        elif provider:
            full_message = f"Configuration error for provider '{provider}': {message}"
        else:
            full_message = f"Configuration error: {message}"
        super().__init__(full_message)


class OrgStartError(Exception):
    """Base error for org start failures."""
    pass


class OrgStructureError(OrgStartError):
    """Org directory structure is invalid."""

    def __init__(self, message: str):
        super().__init__(f"Organization structure error: {message}")


class SessionSpawnError(OrgStartError):
    """Session spawn failed.

    Accepts either a plain worker_id string or a SessionId object as the
    first argument, so it can be raised at both the session provider layer
    and the org-level business logic layer without requiring two classes.
    """

    def __init__(self, worker_id: "str | Any", message: str):
        # Support SessionId objects (have .worker_id attr) as well as plain strings
        if hasattr(worker_id, "worker_id"):
            self.worker_id = str(worker_id.worker_id)
            self.session_id = worker_id
        else:
            self.worker_id = str(worker_id)
            self.session_id = None
        self.cause = message
        super().__init__(f"Failed to spawn session for {self.worker_id}: {message}")


class SessionStartTimeout(OrgStartError):
    """Session did not reach ready state within timeout."""

    def __init__(self, worker_id: str, timeout: int):
        self.worker_id = worker_id
        self.timeout = timeout
        super().__init__(
            f"Session for {worker_id} did not reach ready state within {timeout} seconds"
        )


class ConcurrentModificationError(Exception):
    """Raised when optimistic locking detects a concurrent update.

    This is used to prevent race conditions in delegation operations
    where two processes attempt to modify the same delegation state
    simultaneously.
    """

    def __init__(self, entity_type: str, entity_id: str, message: str | None = None):
        self.entity_type = entity_type
        self.entity_id = entity_id
        if message:
            full_message = f"Concurrent modification of {entity_type} '{entity_id}': {message}"
        else:
            full_message = f"Concurrent modification detected for {entity_type} '{entity_id}'"
        super().__init__(full_message)


class CircularDelegationError(Exception):
    """Raised when a delegation would create a circular reference.

    Circular delegations would allow a worker to grant authority to someone
    who could then delegate back to them, creating an infinite loop.
    """

    def __init__(self, delegator_id: str, delegate_id: str):
        self.delegator_id = delegator_id
        self.delegate_id = delegate_id
        super().__init__(
            f"Delegation from '{delegator_id}' to '{delegate_id}' would create a cycle"
        )


class DelegationNotFoundError(Exception):
    """Raised when an expected delegation grant is not found."""

    def __init__(self, delegate_id: str):
        self.delegate_id = delegate_id
        super().__init__(f"No active delegation found for worker '{delegate_id}'")


# --- Budget domain ---

class BudgetExhaustedError(Exception):
    """Raised when worker budget is exhausted."""

    def __init__(
        self,
        worker_id: str,
        required: float,
        available: float,
        message: str | None = None,
    ):
        self.worker_id = worker_id
        self.required = required
        self.available = available
        if message is None:
            message = (
                f"Budget exhausted for worker '{worker_id}'. "
                f"Required: ${required:.4f}, Available: ${available:.4f}"
            )
        super().__init__(message)


class NoBudgetAllocationError(Exception):
    """Raised when worker has no budget allocation."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        super().__init__(
            f"No budget allocation found for worker '{worker_id}'. "
            "Contact your manager to request budget allocation."
        )


class BudgetAllocationError(Exception):
    """Raised when budget allocation fails."""

    pass


# --- Context domain ---

class OrgContextError(Exception):
    """Base exception for OrgContext errors."""

    pass


class OrgNotFoundError(OrgContextError):
    """Raised when org path doesn't exist or isn't initialized."""

    def __init__(self, org_path: "Path"):
        self.org_path = org_path
        super().__init__(f"Organization not found or not initialized: {org_path}")


# --- Storage domain ---

class StorageError(Exception):
    """Base exception for storage operations."""

    pass


# --- Board rules domain (per quinn-ai-zm8a §11) ---

class RuleEngineError(Exception):
    """Base for all rules-engine errors."""

    pass


class RuleViolation(RuleEngineError):
    """Raised when evaluate_or_raise hits a BLOCK-class decision."""

    def __init__(self, decision: "Any"):
        self.decision = decision
        rule_id = decision.rule.id if decision.rule is not None else "<unknown>"
        super().__init__(
            f"Action blocked by rule '{rule_id}': {decision.message}"
        )


class RuleSetLoadError(RuleEngineError):
    """Loader failed (YAML parse, schema validation, regex compile)."""

    def __init__(self, source_path: "Path | str", message: str):
        self.source_path = source_path
        super().__init__(f"Failed to load rules from {source_path}: {message}")


class RuleEvalTimeout(RuleEngineError):
    """signal.alarm fired during evaluate(). Engine fails closed."""

    def __init__(self, action: str, timeout_seconds: int):
        self.action = action
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Rule evaluation for action '{action}' exceeded {timeout_seconds}s timeout"
        )


# --- Org templates domain (per quinn-ai-u0h2 §9) ---

class TemplateError(Exception):
    """Base for template-system errors."""

    pass


class TemplateNotFound(TemplateError):
    """Named template not in registry."""

    pass


class TemplateMissingParent(TemplateError):
    """Template requires a parent but no parent_team_name was provided."""

    def __init__(self, template_name: str, requires: tuple[str, ...]):
        self.template_name = template_name
        self.requires = requires
        super().__init__(
            f"Template '{template_name}' requires parent of type {list(requires)}; "
            f"pass --under <existing-team-name>"
        )


class TemplateWrongParentType(TemplateError):
    """Parent team's template_type doesn't match the child's `requires`."""

    def __init__(
        self,
        template_name: str,
        parent_team_name: str,
        parent_template_type: "str | None",
        requires: tuple[str, ...],
    ):
        self.template_name = template_name
        self.parent_team_name = parent_team_name
        self.parent_template_type = parent_template_type
        self.requires = requires
        if parent_template_type is None:
            msg = (
                f"Team '{parent_team_name}' predates the templates feature "
                f"(NULL template_type); cannot be referenced as parent. "
                f"Retag it via `qn org templates retag` (out of scope for v0)."
            )
        else:
            msg = (
                f"Template '{template_name}' requires parent of type "
                f"{list(requires)}, but team '{parent_team_name}' has type "
                f"'{parent_template_type}'"
            )
        super().__init__(msg)


class TemplateParentTerminated(TemplateError):
    """Parent team exists but is terminated/inactive."""

    def __init__(self, parent_team_name: str):
        self.parent_team_name = parent_team_name
        super().__init__(
            f"Parent team '{parent_team_name}' is terminated; cannot attach a "
            f"new team under an inactive parent"
        )


class HireTeamRollbackFailed(TemplateError):
    """Rollback itself failed; org is in a partial state — operator must intervene."""

    def __init__(self, original: Exception, rollback_errors: list[Exception]):
        self.original = original
        self.rollback_errors = rollback_errors
        super().__init__(
            f"hire-team failed AND rollback failed. Original: {original}. "
            f"Rollback errors: {len(rollback_errors)} additional exceptions. "
            f"Manual cleanup required."
        )


class ChannelNameCollision(TemplateError):
    """Auto-derived channel name already exists; pick a different team --name."""

    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        super().__init__(
            f"Channel '{channel_name}' already exists. "
            f"Pick a different `--name` for hire-team."
        )

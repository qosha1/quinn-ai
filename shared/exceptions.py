"""
Business logic exceptions for QuinnAI.

These exceptions represent invalid operations or states in the
business logic layer, independent of storage implementation.
"""


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
    """Session spawn failed."""

    def __init__(self, worker_id: str, message: str):
        self.worker_id = worker_id
        super().__init__(f"Failed to spawn session for {worker_id}: {message}")


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

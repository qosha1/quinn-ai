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

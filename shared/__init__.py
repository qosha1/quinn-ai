"""
QuinnAI shared business logic.

This package contains conceptual models and business rules that are
shared across all QuinnAI components (CLI, backend, etc.).

- state_machines: State transition definitions
- exceptions: Business logic exceptions
- provider_types: Provider interfaces and data classes
- wrkr: Pure state machine worker abstraction (import via `from shared.wrkr import ...`)
- pyterm: Terminal session management (import via `from shared.pyterm import ...`)
"""

from .state_machines import (
    LIFECYCLE_TRANSITIONS,
    RUNTIME_TRANSITIONS,
    ORG_TRANSITIONS,
    SESSION_ALLOWED_LIFECYCLES,
    LIFECYCLE_STATES,
    RUNTIME_STATES,
    ORG_STATES,
)

from .exceptions import (
    InvalidStateTransition,
    WorkerNotFound,
    InvalidLifecycleState,
    InvalidOrgTransition,
    OrgNotInitialized,
    ActiveSessionExistsError,
    ConfigurationError,
)

from .provider_types import (
    ModelCapabilities,
    ModelInfo,
    ProviderConfig,
    Message,
    CompletionResult,
    Provider,
    ProviderError,
)

__all__ = [
    # State machines
    "LIFECYCLE_TRANSITIONS",
    "RUNTIME_TRANSITIONS",
    "ORG_TRANSITIONS",
    "SESSION_ALLOWED_LIFECYCLES",
    "LIFECYCLE_STATES",
    "RUNTIME_STATES",
    "ORG_STATES",
    # Exceptions
    "InvalidStateTransition",
    "WorkerNotFound",
    "InvalidLifecycleState",
    "InvalidOrgTransition",
    "OrgNotInitialized",
    "ActiveSessionExistsError",
    "ConfigurationError",
    # Provider types
    "ModelCapabilities",
    "ModelInfo",
    "ProviderConfig",
    "Message",
    "CompletionResult",
    "Provider",
    "ProviderError",
]

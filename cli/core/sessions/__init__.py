"""
Concrete SessionInterface implementations and registry.
"""

from .claude_code import ClaudeCodeSession
from .registry import (
    SessionRegistry,
    AdapterNotFoundError,
    get_default_registry,
    create_default_registry,
    initialize_defaults,
    set_default_registry,
    reset_default_registry,
)

# Spawn strategies
from .spawner import (
    SpawnStrategy,
    SpawnerConfig,
    SpawnResult,
    SpawnError,
    SessionNotFoundError,
    SpawnFailedError,
)
from .subprocess_spawner import SubprocessSpawner
from .tmux_spawner import TmuxSpawner
from .spawner_factory import (
    SpawnerFactory,
    SpawnerNotFoundError,
    get_default_factory,
    set_default_factory,
    reset_default_factory,
)
from .binding_manager import (
    SessionBindingManager,
    SessionBinding,
    WorkerAlreadyBoundError,
    SessionAlreadyBoundError,
    BindingNotFoundError,
    get_binding_manager,
    reset_binding_manager,
)
from .state_sync import (
    SessionStateSync,
    StateSyncConfig,
    get_state_sync,
    reset_state_sync,
)

__all__ = [
    # Adapters
    "ClaudeCodeSession",
    # Registry
    "SessionRegistry",
    "AdapterNotFoundError",
    "get_default_registry",
    "create_default_registry",
    "initialize_defaults",
    "set_default_registry",
    "reset_default_registry",
    # Spawn strategies
    "SpawnStrategy",
    "SpawnerConfig",
    "SpawnResult",
    "SpawnError",
    "SessionNotFoundError",
    "SpawnFailedError",
    "SubprocessSpawner",
    "TmuxSpawner",
    "SpawnerFactory",
    "SpawnerNotFoundError",
    "get_default_factory",
    "set_default_factory",
    "reset_default_factory",
    # Binding manager
    "SessionBindingManager",
    "SessionBinding",
    "WorkerAlreadyBoundError",
    "SessionAlreadyBoundError",
    "BindingNotFoundError",
    "get_binding_manager",
    "reset_binding_manager",
    # State sync
    "SessionStateSync",
    "StateSyncConfig",
    "get_state_sync",
    "reset_state_sync",
]

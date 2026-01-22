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
# Persistence
from .persistence import (
    create_session_record,
    update_session_state,
    atomic_transition_session_state,
    get_session_state_and_version,
    StateTransitionConflictError,
    update_session_pid,
    update_session_tmux_name,
    get_session_by_id,
    get_session_for_worker,
    get_active_sessions,
    get_all_sessions,
    count_active_sessions,
    delete_session_record,
    delete_session_for_worker,
)
# Cleanup
from .cleanup import (
    OrphanedSession,
    CleanupResult,
    TMUX_SESSION_PREFIX,
    find_orphaned_tmux_sessions,
    find_stale_db_sessions,
    find_all_orphans,
    cleanup_orphaned_sessions,
    run_startup_cleanup,
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
    # Persistence
    "create_session_record",
    "update_session_state",
    "atomic_transition_session_state",
    "get_session_state_and_version",
    "StateTransitionConflictError",
    "update_session_pid",
    "update_session_tmux_name",
    "get_session_by_id",
    "get_session_for_worker",
    "get_active_sessions",
    "get_all_sessions",
    "count_active_sessions",
    "delete_session_record",
    "delete_session_for_worker",
    # Cleanup
    "OrphanedSession",
    "CleanupResult",
    "TMUX_SESSION_PREFIX",
    "find_orphaned_tmux_sessions",
    "find_stale_db_sessions",
    "find_all_orphans",
    "cleanup_orphaned_sessions",
    "run_startup_cleanup",
]

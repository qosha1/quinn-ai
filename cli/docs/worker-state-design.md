# Worker State Machine Design

## Overview

Workers have two independent state dimensions:
1. **Lifecycle State** - HR/org-chart state (hiring, firing)
2. **Runtime State** - Process/session state (running, crashed)

## Lifecycle States

```
pending → onboarding → active → offboarding → terminated
```

| State | Description | Can Work? | Transitions To |
|-------|-------------|-----------|----------------|
| `pending` | Hired but not yet started | No | onboarding |
| `onboarding` | Learning, setting up | Limited | active, terminated |
| `active` | Fully operational | Yes | offboarding |
| `offboarding` | Wrapping up, knowledge transfer | Limited | terminated |
| `terminated` | No longer employed | No | (terminal) |

### Lifecycle Transitions

```python
LIFECYCLE_TRANSITIONS = {
    "pending": ["onboarding"],
    "onboarding": ["active", "terminated"],  # Can fail onboarding
    "active": ["offboarding"],
    "offboarding": ["terminated"],
    "terminated": [],  # Terminal state
}
```

### Lifecycle Events

- `hire()` → Creates worker in `pending`
- `start_onboarding()` → `pending` → `onboarding`
- `complete_onboarding()` → `onboarding` → `active`
- `start_offboarding()` → `active` → `offboarding`
- `terminate()` → `offboarding` → `terminated`
- `fail_onboarding()` → `onboarding` → `terminated`

## Runtime States

```
starting → running ⇄ idle → stopped
              ↓
           crashed
```

| State | Description | Session Active? | Transitions To |
|-------|-------------|-----------------|----------------|
| `starting` | Session initializing | Partial | running, crashed |
| `running` | Actively working | Yes | idle, stopped, crashed |
| `idle` | Waiting for work | Yes | running, stopped |
| `stopped` | Gracefully shutdown | No | starting |
| `crashed` | Unexpected termination | No | starting |

### Runtime Transitions

```python
RUNTIME_TRANSITIONS = {
    "starting": ["running", "crashed"],
    "running": ["idle", "stopped", "crashed"],
    "idle": ["running", "stopped"],
    "stopped": ["starting"],
    "crashed": ["starting"],
}
```

### Runtime Events

- `start_session(pid)` → Creates/updates to `starting`
- `session_ready()` → `starting` → `running`
- `begin_work(task_id)` → `idle` → `running`
- `finish_work()` → `running` → `idle`
- `stop_session()` → `running`/`idle` → `stopped`
- `detect_crash()` → any → `crashed`
- `restart_session()` → `stopped`/`crashed` → `starting`

## State Interactions

Lifecycle and runtime are **independent but constrained**:

| Lifecycle | Allowed Runtime States |
|-----------|----------------------|
| pending | (no runtime state) |
| onboarding | starting, running, idle, stopped |
| active | starting, running, idle, stopped |
| offboarding | starting, running, idle, stopped |
| terminated | stopped, crashed (cleanup only) |

### Constraints

1. Cannot start session if lifecycle is `pending`
2. Cannot start session if lifecycle is `terminated`
3. `offboarding` workers complete current work, then stop
4. `terminated` workers have no runtime state

## Worker Class Design

```python
class Worker:
    """Worker with dual state machine."""

    def __init__(self, db: Database, worker_id: str):
        self.db = db
        self.id = worker_id

    # Lifecycle
    @property
    def lifecycle_status(self) -> str: ...

    def start_onboarding(self) -> None: ...
    def complete_onboarding(self) -> None: ...
    def start_offboarding(self) -> None: ...
    def terminate(self) -> None: ...

    # Runtime
    @property
    def runtime_status(self) -> Optional[str]: ...

    def start_session(self, pid: int) -> None: ...
    def session_ready(self) -> None: ...
    def begin_work(self, task_id: str) -> None: ...
    def finish_work(self) -> None: ...
    def stop_session(self) -> None: ...
    def mark_crashed(self) -> None: ...

    # Queries
    @property
    def can_work(self) -> bool: ...

    @property
    def is_session_active(self) -> bool: ...
```

## State Validation

All state transitions are validated:

```python
class InvalidStateTransition(Exception):
    """Raised when attempting invalid state transition."""
    def __init__(self, current: str, attempted: str, valid: list[str]):
        self.current = current
        self.attempted = attempted
        self.valid = valid
        super().__init__(
            f"Cannot transition from '{current}' to '{attempted}'. "
            f"Valid transitions: {valid}"
        )
```

## Database Integration

Uses existing tables from db.py:
- `workers.status` → lifecycle state
- `worker_state.runtime_status` → runtime state
- `worker_state.current_task_id` → current work
- `worker_state.pid` → process tracking for crash detection

## Crash Detection

Monitor via heartbeat:
1. Workers update `worker_state.last_activity` periodically
2. System checks for stale heartbeats
3. If no heartbeat for X seconds, mark as `crashed`
4. On restart, transition from `crashed` → `starting`

## Implementation Order

1. Create `Worker` class with lifecycle transitions
2. Add runtime state management
3. Add state validation
4. Add crash detection helpers
5. Integrate with existing queries.py

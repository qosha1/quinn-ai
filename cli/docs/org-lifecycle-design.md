# Org Lifecycle State Machine Design

## Overview

Organizations have a lifecycle state machine tracking operational status. Unlike workers (which have dual lifecycle + runtime machines), orgs have a single state dimension because the org's "runtime" is the aggregate of its workers' runtimes.

## Lifecycle States

```
uninitialized → initialized → running ⇄ stopped
```

| State | Description | Can Hire? | Workers Active? | Transitions To |
|-------|-------------|-----------|-----------------|----------------|
| `uninitialized` | DB exists, no CEO | No | No | initialized |
| `initialized` | CEO exists, ready to start | Yes (CEO only) | No | running |
| `running` | Org is operational | Yes | Yes | stopped |
| `stopped` | Org paused, can resume | No | No (sessions stopped) | running |

### State Transitions

```python
ORG_TRANSITIONS = {
    "uninitialized": ["initialized"],
    "initialized": ["running"],
    "running": ["stopped"],
    "stopped": ["running"],
}
```

### Lifecycle Events

- `init(ceo_name, ceo_role)` → Creates CEO worker, `uninitialized` → `initialized`
- `start()` → Spawns CEO session, `initialized` → `running` (or `stopped` → `running`)
- `stop()` → Stops all worker sessions gracefully, `running` → `stopped`

## State Constraints

### Uninitialized
- No workers exist
- Cannot start or stop
- Can only init

### Initialized
- Exactly one worker (CEO) exists in `pending` state
- CEO has no manager (root of hierarchy)
- Cannot hire additional workers until running
- Can start to begin operations

### Running
- CEO is in `active` lifecycle with active session
- Workers can be hired/fired
- Communication channels active
- Full operations enabled

### Stopped
- All worker sessions stopped (runtime_status = 'stopped')
- Worker lifecycle states preserved
- No new hires while stopped
- Can resume with start()

## Org Class Design

```python
class Org:
    """Organization with lifecycle state machine."""

    def __init__(self, db: Database):
        self.db = db
        self._state = None

    # Properties
    @property
    def status(self) -> str: ...

    @property
    def ceo(self) -> Optional[Worker]: ...

    @property
    def is_operational(self) -> bool: ...

    # Lifecycle transitions
    def init(self, ceo_name: str, ceo_role: str = "CEO") -> Worker: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...

    # Queries
    @property
    def worker_count(self) -> int: ...

    @property
    def active_session_count(self) -> int: ...
```

## State Validation

All state transitions are validated:

```python
class InvalidOrgTransition(Exception):
    """Raised when attempting invalid org state transition."""
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
    pass
```

## Database Integration

Uses existing `org_state` table:
- `status` → lifecycle state
- `ceo_worker_id` → reference to CEO worker
- `started_at` → timestamp of last start
- `stopped_at` → timestamp of last stop

## Relationship to Workers

| Org State | Worker Lifecycle Allowed | Worker Runtime Allowed |
|-----------|-------------------------|------------------------|
| uninitialized | (none) | (none) |
| initialized | pending (CEO only) | (none) |
| running | all | all |
| stopped | all (frozen) | stopped only |

## Implementation Order

1. Create `Org` class with state property
2. Add transition validation
3. Implement `init()` method
4. Implement `start()` method
5. Implement `stop()` method
6. Add query helpers (worker_count, etc.)
7. Integrate with queries.py

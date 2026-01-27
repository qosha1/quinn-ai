# Session Status Inconsistency Analysis

## Problem Statement

Dashboard shows "1 active session" while Team tab shows CEO as "idle" - creating user confusion about what "active" means.

## Root Cause: Semantic Inconsistency

### Current Definition (Code)
Throughout the codebase, "active session" is defined as:
```python
state IN ('starting', 'running', 'idle')
```

### User Expectation
"Active" means "doing work" - should be:
```python
state IN ('starting', 'running')  # NOT idle
```

## Affected Locations

### 1. **Dashboard Display** (`terminal-app/src/board_ui/services/org_connection.py:351`)
```python
def _get_active_session_count(self) -> int:
    """Get count of active sessions."""
    row = self._db.fetchone(
        """SELECT COUNT(*) as count FROM sessions
           WHERE state IN ('starting', 'running', 'idle')"""  # ← INCLUDES IDLE
    )
```

### 2. **Org Stats** (`cli/core/org.py:401`)
```python
@property
def active_session_count(self) -> int:
    """Active sessions are those in 'starting', 'running', or 'idle' state."""
    row = self.db.fetchone(
        """SELECT COUNT(*) as count FROM sessions
           WHERE state IN ('starting', 'running', 'idle')"""  # ← INCLUDES IDLE
    )
```

### 3. **Session Queries** (`cli/core/sessions/persistence.py:415`)
```python
def count_active_sessions(db: "Database") -> int:
    """Count active sessions.

    Active sessions are those in 'starting', 'running', or 'idle' state.
    """
    row = db.fetchone(
        """SELECT COUNT(*) as count FROM sessions
           WHERE state IN ('starting', 'running', 'idle')"""  # ← INCLUDES IDLE
    )
```

### 4. **Worker Methods** (`cli/core/worker.py:680`)
```python
def is_session_active(self) -> bool:
    """Check if worker session is active.

    Returns True if runtime is 'starting', 'running', or 'idle'.
    """
    return self.runtime_status in ("starting", "running", "idle")  # ← INCLUDES IDLE
```

### 5. **Team View** (`terminal-app/src/board_ui/views/team.py:125`)
```python
# Correctly shows actual state
status_icon = self._get_status_icon(worker.session_state)  # ← Shows "idle" not "active"
```

## Why This is Confusing

| Component | What It Shows | User Sees |
|-----------|---------------|-----------|
| **Dashboard** | "1 active session" | Implies work happening |
| **Team Tab** | "CEO: idle" | Contradicts dashboard |
| **Reality** | Session exists but idle | Truth |

## Session State Taxonomy

### Runtime Status (Actual States)
```python
class RuntimeStatus(str, Enum):
    STARTING = "starting"   # Session starting up
    RUNNING = "running"     # Actively processing
    IDLE = "idle"          # Waiting for work
    STOPPED = "stopped"    # Intentionally stopped
    CRASHED = "crashed"    # Error exit
```

### Semantic Groups (What We Actually Mean)

**Option A: Current Codebase Definition**
- **"Active"** = `starting | running | idle` (session exists)
- **"Inactive"** = `stopped | crashed` (no session)

**Option B: User-Friendly Definition (RECOMMENDED)**
- **"Working"** = `starting | running` (doing work)
- **"Idle"** = `idle` (waiting for work)
- **"Stopped"** = `stopped | crashed` (no session)

## Recommended Solution: Centralized Status Module

### 1. Create `shared/status.py`

```python
"""Centralized session status classification.

This module provides consistent terminology across the codebase for
session states.
"""
from enum import Enum
from typing import Literal

# Import canonical RuntimeStatus
from shared.enums import RuntimeStatus


class SessionStatusGroup(str, Enum):
    """Semantic groupings of runtime status."""
    WORKING = "working"      # Actively doing work
    IDLE = "idle"           # Session exists but waiting
    STOPPED = "stopped"     # No session (stopped or crashed)


def classify_status(runtime_status: RuntimeStatus | str | None) -> SessionStatusGroup:
    """Classify runtime status into semantic group.

    Args:
        runtime_status: Runtime status to classify

    Returns:
        Semantic status group

    Examples:
        >>> classify_status("running")
        SessionStatusGroup.WORKING
        >>> classify_status("idle")
        SessionStatusGroup.IDLE
        >>> classify_status("stopped")
        SessionStatusGroup.STOPPED
    """
    if runtime_status in ("starting", "running"):
        return SessionStatusGroup.WORKING
    elif runtime_status == "idle":
        return SessionStatusGroup.IDLE
    else:
        return SessionStatusGroup.STOPPED


def is_working(runtime_status: RuntimeStatus | str | None) -> bool:
    """Check if session is actively working."""
    return classify_status(runtime_status) == SessionStatusGroup.WORKING


def is_idle(runtime_status: RuntimeStatus | str | None) -> bool:
    """Check if session is idle."""
    return classify_status(runtime_status) == SessionStatusGroup.IDLE


def has_session(runtime_status: RuntimeStatus | str | None) -> bool:
    """Check if worker has an active session (working or idle)."""
    return runtime_status in ("starting", "running", "idle")


# SQL fragments for common queries
SQL_WORKING = "state IN ('starting', 'running')"
SQL_HAS_SESSION = "state IN ('starting', 'running', 'idle')"
SQL_IDLE = "state = 'idle'"
```

### 2. Update All Consumers

**Dashboard** (`terminal-app/src/board_ui/services/org_connection.py`):
```python
from shared.status import SQL_WORKING, SQL_HAS_SESSION

def _get_working_session_count(self) -> int:
    """Get count of sessions actively working."""
    row = self._db.fetchone(
        f"SELECT COUNT(*) as count FROM sessions WHERE {SQL_WORKING}"
    )
    return row["count"] if row else 0

def _get_open_session_count(self) -> int:
    """Get count of open sessions (working or idle)."""
    row = self._db.fetchone(
        f"SELECT COUNT(*) as count FROM sessions WHERE {SQL_HAS_SESSION}"
    )
    return row["count"] if row else 0
```

**Dashboard UI** (`terminal-app/src/board_ui/views/dashboard.py`):
```python
# Show both metrics
yield Label("--", id="working-count", classes="metric-value status-running")
yield Label("working sessions", classes="metric-label")

yield Label("--", id="idle-count", classes="metric-value status-idle")
yield Label("idle sessions", classes="metric-label")
```

**Org Class** (`cli/core/org.py`):
```python
from shared.status import SQL_WORKING, SQL_HAS_SESSION

@property
def working_session_count(self) -> int:
    """Get count of sessions actively working (starting or running)."""
    row = self.db.fetchone(
        f"SELECT COUNT(*) as count FROM sessions WHERE {SQL_WORKING}"
    )
    return row["count"] if row else 0

@property
def open_session_count(self) -> int:
    """Get count of open sessions (working or idle)."""
    row = self.db.fetchone(
        f"SELECT COUNT(*) as count FROM sessions WHERE {SQL_HAS_SESSION}"
    )
    return row["count"] if row else 0
```

**Worker Class** (`cli/core/worker.py`):
```python
from shared.status import is_working, has_session

def is_working(self) -> bool:
    """Check if worker is actively working."""
    return is_working(self.runtime_status)

def has_session(self) -> bool:
    """Check if worker has an open session."""
    return has_session(self.runtime_status)
```

## Implementation Plan

### Phase 1: Add Status Module (Non-Breaking)
1. Create `shared/status.py` with classification functions
2. Add tests in `shared/tests/test_status.py`
3. Document in `docs/architecture/session-states.md`

### Phase 2: Update Queries (Non-Breaking)
1. Update all SQL queries to use `shared.status.SQL_*` constants
2. Maintain backwards compatibility (keep old methods, mark deprecated)
3. Add new methods with clear names (`working_*`, `open_*`)

### Phase 3: Update UI (User-Facing)
1. Dashboard: Show "working sessions" and "idle sessions" separately
2. Team tab: Already correct (no changes needed)
3. Update labels and tooltips for clarity

### Phase 4: Deprecation
1. Mark old `active_session_count` methods as deprecated
2. Update all internal callers to use new methods
3. Remove deprecated methods in next major version

## Benefits

1. **Consistent Terminology**: One source of truth for status classification
2. **Clear Semantics**: "working" vs "idle" vs "stopped" - no ambiguity
3. **Centralized Logic**: All status checks in one place
4. **Easy Testing**: Mock `shared.status` instead of scattered conditions
5. **Better UX**: Dashboard accurately reflects reality

## Migration Strategy

### Backwards Compatibility
```python
# Old (deprecated)
@property
def active_session_count(self) -> int:
    """DEPRECATED: Use working_session_count or open_session_count."""
    warnings.warn(
        "active_session_count is deprecated. Use open_session_count for "
        "all sessions (including idle) or working_session_count for only "
        "active work sessions.",
        DeprecationWarning,
        stacklevel=2
    )
    return self.open_session_count
```

### New API
```python
# New (clear)
@property
def working_session_count(self) -> int:
    """Count of sessions actively working (starting/running)."""
    ...

@property
def open_session_count(self) -> int:
    """Count of open sessions (working + idle)."""
    ...
```

## Testing Requirements

```python
# shared/tests/test_status.py
def test_classify_status_working():
    assert classify_status("starting") == SessionStatusGroup.WORKING
    assert classify_status("running") == SessionStatusGroup.WORKING

def test_classify_status_idle():
    assert classify_status("idle") == SessionStatusGroup.IDLE

def test_classify_status_stopped():
    assert classify_status("stopped") == SessionStatusGroup.STOPPED
    assert classify_status("crashed") == SessionStatusGroup.STOPPED
    assert classify_status(None) == SessionStatusGroup.STOPPED

def test_is_working():
    assert is_working("running") is True
    assert is_working("idle") is False

def test_has_session():
    assert has_session("running") is True
    assert has_session("idle") is True
    assert has_session("stopped") is False
```

## Summary

The current codebase uses "active session" to mean "session exists" (including idle), but users expect "active" to mean "doing work" (excluding idle). This creates confusion.

**Solution**: Create a centralized `shared/status.py` module that provides:
- Clear classification functions
- SQL constants for consistent queries
- Semantic groupings: WORKING | IDLE | STOPPED
- Backwards-compatible migration path

This eliminates terminology confusion and provides a single source of truth for session status classification across the entire codebase.

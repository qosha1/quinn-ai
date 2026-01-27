"""Centralized session status classification.

This module provides consistent terminology across the codebase for
session states, eliminating confusion between "active" (session exists)
and "working" (actively processing).

The problem this solves:
- Old code: "active session" meant starting|running|idle
- User expectation: "active" means doing work (not idle)
- Result: Dashboard shows "1 active" but team shows "idle" - confusing!

New terminology:
- WORKING: starting | running (actively doing work)
- IDLE: idle (session exists, waiting for work)
- STOPPED: stopped | crashed | None (no session)
"""
from enum import Enum
from typing import Optional


class SessionStatusGroup(str, Enum):
    """Semantic groupings of runtime status.

    These groups provide clear, user-friendly classification of what
    a worker session is actually doing.
    """
    WORKING = "working"      # Actively doing work
    IDLE = "idle"           # Session exists but waiting
    STOPPED = "stopped"     # No session (stopped or crashed)


def classify_status(runtime_status: Optional[str]) -> SessionStatusGroup:
    """Classify runtime status into semantic group.

    Args:
        runtime_status: Runtime status value or None

    Returns:
        Semantic status group

    Examples:
        >>> classify_status("running")
        SessionStatusGroup.WORKING
        >>> classify_status("starting")
        SessionStatusGroup.WORKING
        >>> classify_status("idle")
        SessionStatusGroup.IDLE
        >>> classify_status("stopped")
        SessionStatusGroup.STOPPED
        >>> classify_status(None)
        SessionStatusGroup.STOPPED
    """
    if runtime_status in ("starting", "running"):
        return SessionStatusGroup.WORKING
    elif runtime_status == "idle":
        return SessionStatusGroup.IDLE
    else:
        # stopped, crashed, None, or unknown
        return SessionStatusGroup.STOPPED


def is_working(runtime_status: Optional[str]) -> bool:
    """Check if session is actively working.

    Args:
        runtime_status: Runtime status value

    Returns:
        True if starting or running, False otherwise
    """
    return classify_status(runtime_status) == SessionStatusGroup.WORKING


def is_idle(runtime_status: Optional[str]) -> bool:
    """Check if session is idle.

    Args:
        runtime_status: Runtime status value

    Returns:
        True if idle, False otherwise
    """
    return classify_status(runtime_status) == SessionStatusGroup.IDLE


def has_session(runtime_status: Optional[str]) -> bool:
    """Check if worker has an open session (working or idle).

    This is what the old "is_active" checks were doing.

    Args:
        runtime_status: Runtime status value

    Returns:
        True if starting, running, or idle - False otherwise
    """
    return runtime_status in ("starting", "running", "idle")


def is_stopped(runtime_status: Optional[str]) -> bool:
    """Check if session is stopped (no active session).

    Args:
        runtime_status: Runtime status value

    Returns:
        True if stopped, crashed, or None - False otherwise
    """
    return classify_status(runtime_status) == SessionStatusGroup.STOPPED


# SQL fragments for common queries
# Use these in SQL queries for consistency

SQL_WORKING = "state IN ('starting', 'running')"
"""SQL WHERE clause for sessions actively working."""

SQL_HAS_SESSION = "state IN ('starting', 'running', 'idle')"
"""SQL WHERE clause for open sessions (working or idle)."""

SQL_IDLE = "state = 'idle'"
"""SQL WHERE clause for idle sessions."""

SQL_STOPPED = "state IN ('stopped', 'crashed') OR state IS NULL"
"""SQL WHERE clause for stopped sessions."""


# For backwards compatibility with old "active" terminology
SQL_ACTIVE = SQL_HAS_SESSION  # Deprecated: Use SQL_HAS_SESSION
"""DEPRECATED: Use SQL_HAS_SESSION or SQL_WORKING depending on intent."""


def get_display_status(runtime_status: Optional[str]) -> str:
    """Get user-friendly display string for status.

    Args:
        runtime_status: Runtime status value

    Returns:
        Display string suitable for UI
    """
    if is_working(runtime_status):
        return "Working"
    elif is_idle(runtime_status):
        return "Idle"
    else:
        return "Stopped"


def get_status_icon(runtime_status: Optional[str]) -> str:
    """Get emoji icon for status.

    Args:
        runtime_status: Runtime status value

    Returns:
        Emoji icon
    """
    if is_working(runtime_status):
        return "▶"  # Working
    elif is_idle(runtime_status):
        return "⏸"  # Idle
    else:
        return "⏹"  # Stopped

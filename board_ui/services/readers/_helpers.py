"""Shared parsing helpers for org readers."""

from datetime import datetime
from typing import Any, Optional

from ...interfaces.org_connection import SessionState, WorkerStatus

DEFAULT_ORG_ID = "default"


def parse_datetime(value: Any) -> Optional[datetime]:
    """Parse datetime from various formats (datetime, ISO string, None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def parse_worker_status(status_str: str) -> WorkerStatus:
    """Parse worker status string to enum, defaulting to PENDING on unknown."""
    try:
        return WorkerStatus(status_str)
    except ValueError:
        return WorkerStatus.PENDING


def parse_session_state(state_str: Optional[str]) -> Optional[SessionState]:
    """Parse session state string to enum, returning None on unknown/missing."""
    if not state_str:
        return None
    try:
        return SessionState(state_str)
    except ValueError:
        return None

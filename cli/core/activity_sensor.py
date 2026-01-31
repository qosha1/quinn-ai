"""Activity sensor for worker continuation system.

Aggregates activity signals from multiple sources to track when workers are actively working.
This is Phase 1 of the continuation system - just activity sensing, no continuation logic yet.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .db import Database
from .queries.activity import (
    cleanup_old_signals,
    get_recent_signals,
    get_worker_last_activity,
    record_activity_signal,
)


@dataclass
class ActivitySignal:
    """A detected worker activity signal."""

    worker_id: str
    activity_type: str
    signal_strength: int
    metadata: dict
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Set timestamp to now if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ActivitySensor:
    """Aggregates activity signals from multiple sources.

    Tracks worker activity through various signals:
    - Bead updates (strength: 5) - completing work
    - Messages sent (strength: 4) - communicating
    - Code commits (strength: 5) - delivering work
    - File changes (strength: 3) - editing files
    - Session output (strength: 2) - session activity
    - Heartbeat (strength: 1) - staying alive
    """

    def __init__(self, db: Database, org_path: Path):
        """Initialize activity sensor.

        Args:
            db: Database instance
            org_path: Path to org folder
        """
        self.db = db
        self.org_path = org_path

    def record_signal(self, signal: ActivitySignal) -> None:
        """Record an activity signal for a worker.

        Args:
            signal: ActivitySignal to record
        """
        record_activity_signal(
            db=self.db,
            worker_id=signal.worker_id,
            activity_type=signal.activity_type,
            signal_strength=signal.signal_strength,
            metadata=signal.metadata,
        )

    def get_last_activity(
        self,
        worker_id: str,
        min_strength: int = 3,
    ) -> Optional[datetime]:
        """Get timestamp of last meaningful activity.

        Args:
            worker_id: Worker ID
            min_strength: Minimum signal strength to consider (default: 3)

        Returns:
            Timestamp of last activity, or None if no activity found
        """
        return get_worker_last_activity(
            db=self.db,
            worker_id=worker_id,
            min_strength=min_strength,
        )

    def get_recent_signals(
        self,
        worker_id: str,
        minutes: int = 30,
    ) -> list[dict]:
        """Get recent activity signals for a worker.

        Args:
            worker_id: Worker ID
            minutes: How many minutes back to look (default: 30)

        Returns:
            List of activity signal dicts
        """
        return get_recent_signals(
            db=self.db,
            worker_id=worker_id,
            minutes=minutes,
        )

    def cleanup_old_signals(self, retention_hours: int = 24) -> int:
        """Delete old activity signals.

        Args:
            retention_hours: Hours to retain signals (default: 24)

        Returns:
            Number of signals deleted
        """
        return cleanup_old_signals(
            db=self.db,
            retention_hours=retention_hours,
        )


__all__ = [
    "ActivitySignal",
    "ActivitySensor",
]

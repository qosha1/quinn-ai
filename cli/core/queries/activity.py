"""Activity signal queries for worker continuation system."""

import json
from datetime import datetime, timedelta
from typing import Optional

from ..db import Database


def record_activity_signal(
    db: Database,
    worker_id: str,
    activity_type: str,
    signal_strength: int,
    metadata: Optional[dict] = None,
) -> None:
    """Record an activity signal for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        activity_type: Type of activity (bead_update, message_sent, etc.)
        signal_strength: Strength of signal (1-5)
        metadata: Optional metadata dict (will be JSON serialized)

    Raises:
        ValueError: If signal_strength out of range or activity_type invalid
    """
    valid_types = {
        "bead_update",
        "message_sent",
        "code_commit",
        "file_change",
        "session_output",
        "heartbeat",
    }

    if activity_type not in valid_types:
        raise ValueError(
            f"Invalid activity_type '{activity_type}'. "
            f"Must be one of: {', '.join(sorted(valid_types))}"
        )

    if not (1 <= signal_strength <= 5):
        raise ValueError(f"signal_strength must be between 1 and 5, got {signal_strength}")

    metadata_json = json.dumps(metadata) if metadata else None
    now = datetime.now()

    db.execute(
        """INSERT INTO activity_signals
           (worker_id, activity_type, signal_strength, metadata, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (worker_id, activity_type, signal_strength, metadata_json, now),
    )

    # Update worker_state.last_activity if signal is meaningful (strength >= 3)
    if signal_strength >= 3:
        db.execute(
            """UPDATE worker_state
               SET last_activity = ?, updated_at = ?
               WHERE worker_id = ?""",
            (now, now, worker_id),
        )

    db.connection.commit()


def get_worker_last_activity(
    db: Database,
    worker_id: str,
    min_strength: int = 3,
) -> Optional[datetime]:
    """Get timestamp of last meaningful activity for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        min_strength: Minimum signal strength to consider (default: 3)

    Returns:
        Timestamp of last activity, or None if no activity found
    """
    row = db.fetchone(
        """SELECT created_at
           FROM activity_signals
           WHERE worker_id = ? AND signal_strength >= ?
           ORDER BY created_at DESC
           LIMIT 1""",
        (worker_id, min_strength),
    )

    if row:
        return row["created_at"]

    return None


def get_recent_signals(
    db: Database,
    worker_id: str,
    minutes: int = 30,
) -> list[dict]:
    """Get recent activity signals for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        minutes: How many minutes back to look (default: 30)

    Returns:
        List of activity signal dicts with keys:
        - id: Signal ID
        - activity_type: Type of activity
        - signal_strength: Strength (1-5)
        - metadata: Metadata dict (or None)
        - created_at: Timestamp
    """
    since = datetime.now() - timedelta(minutes=minutes)

    rows = db.fetchall(
        """SELECT id, activity_type, signal_strength, metadata, created_at
           FROM activity_signals
           WHERE worker_id = ? AND created_at >= ?
           ORDER BY created_at DESC""",
        (worker_id, since),
    )

    signals = []
    for row in rows:
        metadata = None
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                pass

        signals.append(
            {
                "id": row["id"],
                "activity_type": row["activity_type"],
                "signal_strength": row["signal_strength"],
                "metadata": metadata,
                "created_at": row["created_at"],
            }
        )

    return signals


def cleanup_old_signals(
    db: Database,
    retention_hours: int = 24,
) -> int:
    """Delete old activity signals beyond retention period.

    Args:
        db: Database instance
        retention_hours: Hours to retain signals (default: 24)

    Returns:
        Number of signals deleted
    """
    cutoff = datetime.now() - timedelta(hours=retention_hours)

    cursor = db.execute(
        "DELETE FROM activity_signals WHERE created_at < ?",
        (cutoff,),
    )
    db.connection.commit()

    return cursor.rowcount


__all__ = [
    "record_activity_signal",
    "get_worker_last_activity",
    "get_recent_signals",
    "cleanup_old_signals",
]

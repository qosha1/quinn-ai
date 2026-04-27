"""Read recent activity from per-worker JSONL log files."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ...logging_config import get_board_logger

logger = get_board_logger(__name__)


class ActivityReader:
    """Read recent activity events from live/logs/activity/*.jsonl."""

    def __init__(self, db: Any, org_path: Path) -> None:
        self._org_path = org_path

    def get_recent_activity(self, minutes: int = 30, limit: int = 50) -> list[dict]:
        """Get recent activity from all workers."""
        activity_dir = self._org_path / "live" / "logs" / "activity"
        if not activity_dir.exists():
            return []

        cutoff = datetime.now() - timedelta(minutes=minutes)
        all_activities: list[dict] = []

        for activity_file in activity_dir.glob("*.jsonl"):
            try:
                with open(activity_file, "r") as f:
                    for line in f:
                        try:
                            activity = json.loads(line)
                            activity_time = datetime.fromisoformat(activity["timestamp"])
                            if activity_time >= cutoff:
                                all_activities.append(activity)
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
            except Exception as e:
                logger.warning(f"Failed to read activity file {activity_file}: {e}")
                continue

        all_activities.sort(key=lambda x: x["timestamp"], reverse=True)
        return all_activities[:limit]

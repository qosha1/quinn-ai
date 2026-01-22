"""
Communication types for inter-worker messaging.

WorkerMessage: Permanent knowledge units (stored in beads/quinn.db)
Notification: Ephemeral work pointers with urgency (auto-cleanup after actioning)

These types integrate with the beads system where:
- Messages are Issues with sender, time_sensitivity, ephemeral fields
- Threading uses replies-to dependency with thread_id
- Notifications use gate fields (AwaitType, Waiters, Timeout)

Note: All types are imported from shared.core.message for canonical source.
"""

from __future__ import annotations

# Import canonical types from shared.core.message
from shared.core.message import (
    MessageType,
    TimeSensitivity,
    WorkerMessage,
    Notification,
)

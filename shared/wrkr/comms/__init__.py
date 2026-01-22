"""
Communications module for wrkr inter-worker messaging.

Provides:
- WorkerMessage: Permanent knowledge units (messages between workers)
- Notification: Ephemeral work pointers with urgency
- Inbox: Message receiving interface
- Outbox: Message sending interface
- NotificationHandler: Task conversion and interrupt handling

All types integrate with the beads system where messages are stored as Issues.
"""

from shared.wrkr.comms.types import (
    MessageType,
    Notification,
    TimeSensitivity,
    WorkerMessage,
)
from shared.wrkr.comms.inbox import (
    BaseInbox,
    BeadsInbox,
    InboxInterface,
    InMemoryInbox,
)
from shared.wrkr.comms.outbox import (
    BaseOutbox,
    BeadsOutbox,
    InMemoryOutbox,
    OutboxInterface,
)
from shared.wrkr.comms.notifications import (
    BeadsNotificationHandler,
    InMemoryNotificationHandler,
    NotificationHandler,
    NotificationHandlerInterface,
    TaskConversionResult,
    UrgentInterrupt,
)

__all__ = [
    # Types
    "MessageType",
    "Notification",
    "TimeSensitivity",
    "WorkerMessage",
    # Inbox
    "BaseInbox",
    "BeadsInbox",
    "InboxInterface",
    "InMemoryInbox",
    # Outbox
    "BaseOutbox",
    "BeadsOutbox",
    "InMemoryOutbox",
    "OutboxInterface",
    # Notifications
    "BeadsNotificationHandler",
    "InMemoryNotificationHandler",
    "NotificationHandler",
    "NotificationHandlerInterface",
    "TaskConversionResult",
    "UrgentInterrupt",
]

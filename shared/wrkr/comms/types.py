"""
Communication types for inter-worker messaging.

WorkerMessage: Permanent knowledge units (stored in beads/quinn.db)
Notification: Ephemeral work pointers with urgency (auto-cleanup after actioning)

These types integrate with the beads system where:
- Messages are Issues with sender, time_sensitivity, ephemeral fields
- Threading uses replies-to dependency with thread_id
- Notifications use gate fields (AwaitType, Waiters, Timeout)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


class TimeSensitivity(Enum):
    """Urgency level for messages and notifications.

    Maps to beads time_sensitivity field.
    """

    IMMEDIATE = "immediate"  # Must handle now, interrupts current work
    HOURS = "hours"          # Handle within hours
    DAYS = "days"            # Handle within days
    WEEKS = "weeks"          # Handle within weeks
    WHENEVER = "whenever"    # No urgency, handle when convenient


class MessageType(Enum):
    """Type of inter-worker message."""

    REQUEST = "request"      # Ask/question requiring response
    RESPONSE = "response"    # Reply to a request
    INFORM = "inform"        # FYI, no response needed
    ESCALATION = "escalation"  # Problem escalated from below
    DELEGATION = "delegation"  # Work assigned from above
    BROADCAST = "broadcast"  # Fan-out to multiple recipients


@dataclass
class WorkerMessage:
    """
    A message between workers in the organization.

    Messages are permanent knowledge units stored in beads as Issues.
    They form searchable conversation history with threading support.

    Attributes:
        id: Unique message ID (beads issue ID, e.g., "bd-xxxx")
        sender: Worker ID who sent the message
        recipients: List of worker IDs to receive the message
        subject: Brief summary/title of the message
        body: Full message content
        message_type: Type of message (request, response, etc.)
        time_sensitivity: How urgently this needs attention
        thread_id: ID of the conversation thread (for replies)
        reply_to: ID of the message this replies to (if any)
        ask_id: Optional link to originating Ask
        okr_id: Optional link to strategic OKR
        ephemeral: If True, auto-delete after actioning
        metadata: Additional key-value data
        created_at: When the message was created
    """

    id: str
    sender: str
    recipients: list[str]
    subject: str
    body: str
    message_type: MessageType = MessageType.INFORM
    time_sensitivity: TimeSensitivity = TimeSensitivity.WHENEVER
    thread_id: str | None = None
    reply_to: str | None = None
    ask_id: str | None = None
    okr_id: str | None = None
    ephemeral: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def request(
        cls,
        id: str,
        sender: str,
        recipients: list[str],
        subject: str,
        body: str,
        time_sensitivity: TimeSensitivity = TimeSensitivity.DAYS,
        **kwargs,
    ) -> WorkerMessage:
        """Create a request message requiring a response."""
        return cls(
            id=id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body=body,
            message_type=MessageType.REQUEST,
            time_sensitivity=time_sensitivity,
            **kwargs,
        )

    @classmethod
    def response(
        cls,
        id: str,
        sender: str,
        recipients: list[str],
        subject: str,
        body: str,
        reply_to: str,
        thread_id: str | None = None,
        **kwargs,
    ) -> WorkerMessage:
        """Create a response to a previous message."""
        return cls(
            id=id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body=body,
            message_type=MessageType.RESPONSE,
            reply_to=reply_to,
            thread_id=thread_id,
            **kwargs,
        )

    @classmethod
    def escalation(
        cls,
        id: str,
        sender: str,
        recipients: list[str],
        subject: str,
        body: str,
        time_sensitivity: TimeSensitivity = TimeSensitivity.HOURS,
        **kwargs,
    ) -> WorkerMessage:
        """Create an escalation message for problems needing help."""
        return cls(
            id=id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body=body,
            message_type=MessageType.ESCALATION,
            time_sensitivity=time_sensitivity,
            **kwargs,
        )

    @classmethod
    def delegation(
        cls,
        id: str,
        sender: str,
        recipients: list[str],
        subject: str,
        body: str,
        ask_id: str | None = None,
        okr_id: str | None = None,
        **kwargs,
    ) -> WorkerMessage:
        """Create a delegation message assigning work."""
        return cls(
            id=id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body=body,
            message_type=MessageType.DELEGATION,
            ask_id=ask_id,
            okr_id=okr_id,
            **kwargs,
        )

    def is_urgent(self) -> bool:
        """Check if message requires immediate attention."""
        return self.time_sensitivity == TimeSensitivity.IMMEDIATE

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "sender": self.sender,
            "recipients": self.recipients,
            "subject": self.subject,
            "body": self.body,
            "message_type": self.message_type.value,
            "time_sensitivity": self.time_sensitivity.value,
            "thread_id": self.thread_id,
            "reply_to": self.reply_to,
            "ask_id": self.ask_id,
            "okr_id": self.okr_id,
            "ephemeral": self.ephemeral,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Notification:
    """
    An ephemeral notification pointing to work.

    Notifications are lightweight pointers to messages or tasks that
    require attention. They auto-cleanup after the worker actions them.

    Unlike messages (permanent knowledge), notifications are work signals
    that disappear once processed.

    Attributes:
        id: Unique notification ID
        worker_id: Worker who should receive this notification
        message_id: Optional ID of the message this points to
        task_id: Optional ID of the task this points to
        title: Brief notification text
        time_sensitivity: How urgently this needs attention
        source: Where this notification came from
        created_at: When the notification was created
        expires_at: When the notification auto-expires (None = never)
        metadata: Additional data
    """

    id: str
    worker_id: str
    title: str
    time_sensitivity: TimeSensitivity = TimeSensitivity.WHENEVER
    message_id: str | None = None
    task_id: str | None = None
    source: Literal["inbox", "queue", "escalation", "system"] = "system"
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_urgent(self) -> bool:
        """Check if notification requires immediate interruption."""
        return self.time_sensitivity == TimeSensitivity.IMMEDIATE

    def is_expired(self) -> bool:
        """Check if notification has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def points_to_message(self) -> bool:
        """Check if this notification points to a message."""
        return self.message_id is not None

    def points_to_task(self) -> bool:
        """Check if this notification points to a task."""
        return self.task_id is not None

    @classmethod
    def from_message(
        cls,
        id: str,
        message: WorkerMessage,
        worker_id: str,
    ) -> Notification:
        """Create a notification from a message."""
        return cls(
            id=id,
            worker_id=worker_id,
            title=f"{message.message_type.value.title()}: {message.subject}",
            time_sensitivity=message.time_sensitivity,
            message_id=message.id,
            source="inbox",
            metadata={"sender": message.sender},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "worker_id": self.worker_id,
            "title": self.title,
            "time_sensitivity": self.time_sensitivity.value,
            "message_id": self.message_id,
            "task_id": self.task_id,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }

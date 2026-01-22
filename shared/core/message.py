"""
Canonical message types for QuinnAI.

Per CLAUDE.md: "One Protocol For Everything. All communication through same interface."

Message Types:
    Message: Base message with role + content (for provider API)
    WorkerMessage: Extended message with routing (sender, recipients, threading)
    ConversationMessage: Message with turn tracking and tool calls

The hierarchy supports:
    - Provider API calls (Message)
    - Inter-worker communication (WorkerMessage)
    - Session transcripts (ConversationMessage)

All higher-level types build on Message as the base unit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


# =============================================================================
# Enums
# =============================================================================


class MessageRole(Enum):
    """Role of message sender."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class MessageType(Enum):
    """Type of inter-worker message."""

    REQUEST = "request"  # Ask/question requiring response
    RESPONSE = "response"  # Reply to a request
    INFORM = "inform"  # FYI, no response needed
    ESCALATION = "escalation"  # Problem escalated from below
    DELEGATION = "delegation"  # Work assigned from above
    BROADCAST = "broadcast"  # Fan-out to multiple recipients


class TimeSensitivity(Enum):
    """Urgency level for messages."""

    IMMEDIATE = "immediate"  # Must handle now, interrupts current work
    HOURS = "hours"  # Handle within hours
    DAYS = "days"  # Handle within days
    WEEKS = "weeks"  # Handle within weeks
    WHENEVER = "whenever"  # No urgency, handle when convenient


# =============================================================================
# Base Message - For Provider API
# =============================================================================


@dataclass
class Message:
    """Base message for provider API calls.

    This is the simplest message type, used for direct provider interactions.
    Contains only role and content - the minimum needed for API calls.
    """

    role: str | MessageRole
    """Role: 'user', 'assistant', 'system', or MessageRole enum."""

    content: str
    """Message content."""

    def __post_init__(self):
        # Normalize role to string for API compatibility
        if isinstance(self.role, MessageRole):
            self.role = self.role.value

    @classmethod
    def user(cls, content: str) -> Message:
        """Create a user message."""
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> Message:
        """Create an assistant message."""
        return cls(role="assistant", content=content)

    @classmethod
    def system(cls, content: str) -> Message:
        """Create a system message."""
        return cls(role="system", content=content)

    def to_dict(self) -> dict[str, str]:
        """Convert to API-compatible dict."""
        role = self.role.value if isinstance(self.role, MessageRole) else self.role
        return {"role": role, "content": self.content}


# =============================================================================
# WorkerMessage - For Inter-Worker Communication
# =============================================================================


@dataclass
class WorkerMessage:
    """Message between workers in the organization.

    Extends base Message with routing, threading, and work dimension links.
    Used for inbox, outbox, and notification systems.
    """

    id: str
    """Unique message ID (e.g., 'msg-xxxx')."""

    sender: str
    """Worker ID who sent the message."""

    recipients: list[str]
    """List of worker IDs to receive the message."""

    subject: str
    """Brief summary/title of the message."""

    body: str
    """Full message content."""

    message_type: MessageType = MessageType.INFORM
    """Type of message (request, response, etc.)."""

    time_sensitivity: TimeSensitivity = TimeSensitivity.WHENEVER
    """How urgently this needs attention."""

    # Threading
    thread_id: str | None = None
    """ID of the conversation thread (for replies)."""

    reply_to: str | None = None
    """ID of the message this replies to (if any)."""

    # Work dimensions
    ask_id: str | None = None
    """Optional link to originating Ask."""

    okr_id: str | None = None
    """Optional link to strategic OKR."""

    # Storage context (for DB persistence)
    channel_id: str | None = None
    """Channel this message belongs to."""

    parent_id: str | None = None
    """Parent message ID (for nested threads)."""

    # Metadata
    ephemeral: bool = False
    """If True, auto-delete after actioning."""

    priority: int = 2
    """Priority level (0=highest, 4=lowest)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional key-value data."""

    created_at: datetime = field(default_factory=datetime.now)
    """When the message was created."""

    # Convenience constructors
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
        """Create an escalation message."""
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

    def to_base_message(self) -> Message:
        """Convert to base Message for API calls."""
        return Message(role="user", content=self.body)

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
            "channel_id": self.channel_id,
            "parent_id": self.parent_id,
            "ephemeral": self.ephemeral,
            "priority": self.priority,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# Notification - Ephemeral Work Pointer
# =============================================================================


@dataclass
class Notification:
    """Ephemeral notification pointing to work.

    Notifications are lightweight pointers to messages or tasks that
    require attention. They auto-cleanup after the worker actions them.
    """

    id: str
    """Unique notification ID."""

    worker_id: str
    """Worker who should receive this notification."""

    title: str
    """Brief notification text."""

    time_sensitivity: TimeSensitivity = TimeSensitivity.WHENEVER
    """How urgently this needs attention."""

    message_id: str | None = None
    """Optional ID of the message this points to."""

    task_id: str | None = None
    """Optional ID of the task this points to."""

    source: Literal["inbox", "queue", "escalation", "system"] = "system"
    """Where this notification came from."""

    created_at: datetime = field(default_factory=datetime.now)
    """When the notification was created."""

    expires_at: datetime | None = None
    """When the notification auto-expires (None = never)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional data."""

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


# =============================================================================
# ConversationMessage - For Transcripts
# =============================================================================


@dataclass
class ToolCall:
    """A tool call made by the assistant."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ToolResult:
    """Result from a tool execution."""

    tool_call_id: str
    output: str
    success: bool = True
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "tool_call_id": self.tool_call_id,
            "output": self.output,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ConversationMessage:
    """Message in a conversation transcript.

    Extends base Message with tool call support and metadata for
    session transcript tracking.
    """

    role: MessageRole
    """Message role."""

    content: str
    """Message content."""

    timestamp: datetime = field(default_factory=datetime.now)
    """When message was created."""

    tool_call: ToolCall | None = None
    """Tool call if this is a tool_call message."""

    tool_result: ToolResult | None = None
    """Tool result if this is a tool_result message."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""

    def to_base_message(self) -> Message:
        """Convert to base Message for API calls."""
        return Message(role=self.role.value, content=self.content)

    def to_dict(self) -> dict:
        result = {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
        if self.tool_call:
            result["tool_call"] = self.tool_call.to_dict()
        if self.tool_result:
            result["tool_result"] = self.tool_result.to_dict()
        return result

    @classmethod
    def user(cls, content: str, **metadata) -> ConversationMessage:
        """Create a user message."""
        return cls(role=MessageRole.USER, content=content, metadata=metadata)

    @classmethod
    def assistant(cls, content: str, **metadata) -> ConversationMessage:
        """Create an assistant message."""
        return cls(role=MessageRole.ASSISTANT, content=content, metadata=metadata)

    @classmethod
    def from_tool_call(cls, tool_call: ToolCall) -> ConversationMessage:
        """Create a message from a tool call."""
        return cls(
            role=MessageRole.TOOL_CALL,
            content=f"Tool: {tool_call.name}",
            tool_call=tool_call,
            timestamp=tool_call.timestamp,
        )

    @classmethod
    def from_tool_result(cls, tool_result: ToolResult) -> ConversationMessage:
        """Create a message from a tool result."""
        preview = (
            tool_result.output[:100] + "..."
            if len(tool_result.output) > 100
            else tool_result.output
        )
        return cls(
            role=MessageRole.TOOL_RESULT,
            content=preview,
            tool_result=tool_result,
            timestamp=tool_result.timestamp,
        )

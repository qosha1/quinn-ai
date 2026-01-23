"""
Worker outbox for sending messages.

OutboxInterface: Protocol for message sending
BeadsOutbox: Implementation that creates beads issues for messages

Workers send messages to teammates, managers, or broadcast to groups.
Messages are persisted in beads and create notifications for recipients.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol
import uuid

from shared.comms.types import (
    MessageType,
    TimeSensitivity,
    WorkerMessage,
)

logger = logging.getLogger(__name__)


class OutboxInterface(Protocol):
    """Protocol for worker message outbox.

    Outbox handles sending messages to other workers,
    threading conversations, and managing sent messages.
    """

    def send(self, message: WorkerMessage) -> str:
        """Send a message to recipients.

        Args:
            message: The message to send.

        Returns:
            The message ID (may be updated from input if generated).
        """
        ...

    def reply(
        self,
        original_message_id: str,
        body: str,
        subject: str | None = None,
    ) -> str:
        """Reply to an existing message.

        Args:
            original_message_id: ID of the message to reply to.
            body: Reply content.
            subject: Optional subject (defaults to "Re: <original subject>").

        Returns:
            The reply message ID.
        """
        ...

    def broadcast(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        time_sensitivity: TimeSensitivity = TimeSensitivity.WHENEVER,
    ) -> list[str]:
        """Send a broadcast message to multiple recipients.

        Creates individual message copies for each recipient.

        Args:
            recipients: List of worker IDs to send to.
            subject: Message subject.
            body: Message body.
            time_sensitivity: Urgency level.

        Returns:
            List of message IDs created.
        """
        ...

    def get_sent(self, limit: int = 10) -> list[WorkerMessage]:
        """Get recently sent messages.

        Args:
            limit: Maximum number of messages to return.

        Returns:
            List of sent messages, most recent first.
        """
        ...


class BaseOutbox(ABC):
    """Base class for outbox implementations.

    Provides common message construction logic.
    Subclasses implement storage-specific send methods.
    """

    def __init__(self, worker_id: str):
        """Initialize outbox for a specific worker.

        Args:
            worker_id: The worker ID this outbox belongs to.
        """
        self._worker_id = worker_id

    @property
    def worker_id(self) -> str:
        """The worker ID this outbox belongs to."""
        return self._worker_id

    @abstractmethod
    def _store_message(self, message: WorkerMessage) -> str:
        """Store a message in the backend.

        Args:
            message: The message to store.

        Returns:
            The assigned message ID.
        """
        pass

    @abstractmethod
    def _get_message(self, message_id: str) -> WorkerMessage | None:
        """Retrieve a message by ID.

        Args:
            message_id: The message ID to retrieve.

        Returns:
            The message, or None if not found.
        """
        pass

    @abstractmethod
    def _fetch_sent(self, limit: int) -> list[WorkerMessage]:
        """Fetch sent messages from storage.

        Args:
            limit: Maximum number to return.

        Returns:
            List of sent messages.
        """
        pass

    def _generate_id(self) -> str:
        """Generate a unique message ID.

        Returns:
            A unique ID string.
        """
        return f"msg-{uuid.uuid4().hex[:8]}"

    def send(self, message: WorkerMessage) -> str:
        """Send a message to recipients.

        Args:
            message: The message to send.

        Returns:
            The message ID.
        """
        # Ensure message has sender set
        if not message.sender:
            message.sender = self._worker_id

        # Generate ID if not set
        if not message.id:
            message.id = self._generate_id()

        return self._store_message(message)

    def reply(
        self,
        original_message_id: str,
        body: str,
        subject: str | None = None,
    ) -> str:
        """Reply to an existing message.

        Args:
            original_message_id: ID of the message to reply to.
            body: Reply content.
            subject: Optional subject override.

        Returns:
            The reply message ID.

        Raises:
            ValueError: If original message not found.
        """
        original = self._get_message(original_message_id)
        if not original:
            raise ValueError(f"Original message not found: {original_message_id}")

        # Determine reply recipients (original sender + any other recipients except self)
        recipients = [original.sender]
        for r in original.recipients:
            if r != self._worker_id and r not in recipients:
                recipients.append(r)

        # Determine thread ID (use existing or start new thread)
        thread_id = original.thread_id or original.id

        # Create reply subject
        reply_subject = subject or f"Re: {original.subject}"

        reply = WorkerMessage.response(
            id=self._generate_id(),
            sender=self._worker_id,
            recipients=recipients,
            subject=reply_subject,
            body=body,
            reply_to=original_message_id,
            thread_id=thread_id,
            ask_id=original.ask_id,  # Inherit work dimensions
            okr_id=original.okr_id,
        )

        return self.send(reply)

    def broadcast(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        time_sensitivity: TimeSensitivity = TimeSensitivity.WHENEVER,
    ) -> list[str]:
        """Send a broadcast to multiple recipients.

        Creates one message with all recipients (fan-out at delivery).

        Args:
            recipients: List of worker IDs.
            subject: Message subject.
            body: Message body.
            time_sensitivity: Urgency level.

        Returns:
            List containing the single broadcast message ID.
        """
        message = WorkerMessage(
            id=self._generate_id(),
            sender=self._worker_id,
            recipients=recipients,
            subject=subject,
            body=body,
            message_type=MessageType.BROADCAST,
            time_sensitivity=time_sensitivity,
        )

        message_id = self.send(message)
        return [message_id]

    def get_sent(self, limit: int = 10) -> list[WorkerMessage]:
        """Get recently sent messages.

        Args:
            limit: Maximum number to return.

        Returns:
            List of sent messages, most recent first.
        """
        return self._fetch_sent(limit)


class InMemoryOutbox(BaseOutbox):
    """In-memory outbox for testing.

    Stores messages in a list without persistence.
    Can be linked to InMemoryInbox instances for message delivery.
    """

    def __init__(self, worker_id: str):
        super().__init__(worker_id)
        self._sent: list[WorkerMessage] = []
        self._inboxes: dict[str, Any] = {}  # worker_id -> InMemoryInbox

    def link_inbox(self, inbox: Any) -> None:
        """Link an inbox for message delivery.

        Args:
            inbox: An InMemoryInbox instance to deliver messages to.
        """
        self._inboxes[inbox.worker_id] = inbox

    def _store_message(self, message: WorkerMessage) -> str:
        """Store message and deliver to recipient inboxes."""
        self._sent.append(message)

        # Deliver to any linked inboxes
        for recipient in message.recipients:
            if recipient in self._inboxes:
                self._inboxes[recipient].add_message(message)

        return message.id

    def _get_message(self, message_id: str) -> WorkerMessage | None:
        """Find a message by ID in sent messages."""
        for msg in self._sent:
            if msg.id == message_id:
                return msg
        return None

    def _fetch_sent(self, limit: int) -> list[WorkerMessage]:
        """Return recently sent messages."""
        return sorted(self._sent, key=lambda m: m.created_at, reverse=True)[:limit]


class BeadsOutbox(BaseOutbox):
    """Outbox implementation that creates beads issues.

    Messages are stored as Issues in the beads system with:
    - type: message
    - sender: worker_id
    - assignee: recipient (one issue per recipient for broadcasts)
    - time_sensitivity: from message
    - ephemeral: from message
    """

    def __init__(
        self,
        worker_id: str,
        bd_command: str = "bd",
        db_path: str | None = None,
        bd_client: Any | None = None,
    ):
        """Initialize beads outbox.

        Args:
            worker_id: The worker ID this outbox belongs to.
            bd_command: Path to bd command.
            db_path: Optional database path override.
            bd_client: Optional BdClient instance (preferred over bd_command/db_path).
        """
        super().__init__(worker_id)
        if bd_client is not None:
            self._bd_client = bd_client
        else:
            from shared.bd import BdClient

            self._bd_client = BdClient(bd_command=bd_command, db_path=db_path)

    def _run_bd(self, *args: str) -> str:
        """Run a bd command and return output."""
        from shared.bd import BdClientError

        try:
            return self._bd_client.run(*args)
        except BdClientError as e:
            raise RuntimeError(str(e)) from e

    def _store_message(self, message: WorkerMessage) -> str:
        """Create beads issue for the message.

        For multiple recipients, creates one issue with assignee set
        to first recipient. Fan-out happens at notification level.
        """
        import json

        # Build bd create arguments
        args = [
            "create",
            f"--title={message.subject}",
            "--type=message",
            f"--priority=2",  # Default priority
        ]

        if message.recipients:
            args.append(f"--assignee={message.recipients[0]}")

        if message.body:
            args.append(f"--description={message.body}")

        # Add message metadata
        metadata = {
            "sender": message.sender,
            "message_type": message.message_type.value,
            "recipients": message.recipients,
            **message.metadata,
        }
        args.append(f"--metadata={json.dumps(metadata)}")

        if message.time_sensitivity != TimeSensitivity.WHENEVER:
            args.append(f"--time-sensitivity={message.time_sensitivity.value}")

        if message.ephemeral:
            args.append("--ephemeral")

        if message.reply_to:
            args.append(f"--reply-to={message.reply_to}")

        if message.ask_id:
            args.append(f"--spawned-from={message.ask_id}")

        if message.okr_id:
            args.append(f"--serves={message.okr_id}")

        try:
            output = self._run_bd(*args)
            # Parse created issue ID from output
            # Expected format: "Created issue: bd-xxxx"
            for line in output.split("\n"):
                if "bd-" in line:
                    parts = line.split()
                    for part in parts:
                        if part.startswith("bd-"):
                            return part.rstrip(":")
            return message.id
        except RuntimeError as e:
            logger.warning("Failed to persist message %s: %s", message.id, e)
            return message.id

    def _get_message(self, message_id: str) -> WorkerMessage | None:
        """Retrieve message from beads."""
        import json
        from datetime import datetime

        try:
            output = self._run_bd("show", message_id, "--json")
            issue = json.loads(output)
        except (RuntimeError, json.JSONDecodeError) as e:
            logger.warning("Failed to retrieve message %s: %s", message_id, e)
            return None

        metadata = issue.get("metadata", {})
        return WorkerMessage(
            id=issue["id"],
            sender=metadata.get("sender", ""),
            recipients=metadata.get("recipients", []),
            subject=issue.get("title", ""),
            body=issue.get("description", ""),
            message_type=MessageType(metadata.get("message_type", "inform")),
            time_sensitivity=TimeSensitivity(
                issue.get("time_sensitivity", "whenever")
            ),
            thread_id=issue.get("thread_id"),
            reply_to=issue.get("reply_to"),
            ask_id=issue.get("ask_id"),
            okr_id=issue.get("okr_id"),
            ephemeral=issue.get("ephemeral", False),
            metadata=metadata,
            created_at=datetime.fromisoformat(issue["created_at"])
            if issue.get("created_at")
            else datetime.now(),
        )

    def _fetch_sent(self, limit: int) -> list[WorkerMessage]:
        """Fetch sent messages from beads."""
        import json
        from datetime import datetime

        try:
            output = self._run_bd(
                "list", "--json", f"--sender={self._worker_id}", f"--limit={limit}"
            )
            issues = json.loads(output) if output.strip() else []
        except (RuntimeError, json.JSONDecodeError) as e:
            logger.warning("Failed to fetch sent messages for worker %s: %s", self._worker_id, e)
            return []

        messages = []
        for issue in issues:
            metadata = issue.get("metadata", {})
            messages.append(
                WorkerMessage(
                    id=issue["id"],
                    sender=metadata.get("sender", self._worker_id),
                    recipients=metadata.get("recipients", []),
                    subject=issue.get("title", ""),
                    body=issue.get("description", ""),
                    message_type=MessageType(metadata.get("message_type", "inform")),
                    time_sensitivity=TimeSensitivity(
                        issue.get("time_sensitivity", "whenever")
                    ),
                    thread_id=issue.get("thread_id"),
                    reply_to=issue.get("reply_to"),
                    ephemeral=issue.get("ephemeral", False),
                    metadata=metadata,
                    created_at=datetime.fromisoformat(issue["created_at"])
                    if issue.get("created_at")
                    else datetime.now(),
                )
            )

        return sorted(messages, key=lambda m: m.created_at, reverse=True)

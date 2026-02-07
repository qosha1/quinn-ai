"""Interfaces for org-layer messaging and escalation.

Defines protocols that allow the shared/org layer to interact with
cli/core services without creating import cycles.
"""

from typing import Protocol, Optional


class MessageCreator(Protocol):
    """Protocol for creating board messages.

    Allows escalation layer to create messages without importing cli/ code.
    This breaks the import cycle between shared/org and cli/core.
    """

    def create_board_message(
        self,
        channel_name: str,
        from_worker_id: str,
        content: str,
        priority: int,
        time_sensitivity: str,
    ) -> Optional[str]:
        """Create a message in a board channel.

        Args:
            channel_name: Name of channel (e.g., "board-channel")
            from_worker_id: ID of worker sending message
            content: Message content (markdown)
            priority: Message priority (0-4)
            time_sensitivity: When to deliver ("immediate", "hours", "days", "whenever")

        Returns:
            Message ID if successful, None if failed
        """
        ...

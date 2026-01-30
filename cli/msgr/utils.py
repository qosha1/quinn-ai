"""
Utility functions for msgr CLI.

Provides channel name resolution and helper functions.
"""

from typing import Optional
from core.db import Database
from core.queries.channel import (
    get_channel,
    get_channel_by_name,
    get_or_create_direct_channel,
)
from core.queries.worker import get_worker


class ChannelResolutionError(Exception):
    """Raised when channel resolution fails."""
    pass


def resolve_channel(
    db: Database,
    channel_ref: str,
    current_worker_id: str,
) -> str:
    """Resolve a channel reference to a channel ID.

    Supports three formats:
    - #channel-name: Look up channel by name
    - @worker-id: Find or create DM channel with worker
    - channel-id: Pass through (assume already an ID)

    Args:
        db: Database instance
        channel_ref: Channel reference (#general, @alice, or chan-123)
        current_worker_id: ID of the worker making the request

    Returns:
        Channel ID

    Raises:
        ChannelResolutionError: If channel cannot be resolved

    Examples:
        >>> resolve_channel(db, '#general', 'worker-123')
        'chan-abc'
        >>> resolve_channel(db, '@alice', 'worker-123')
        'dm-alice-worker'
        >>> resolve_channel(db, 'chan-xyz', 'worker-123')
        'chan-xyz'
    """
    if not channel_ref:
        raise ChannelResolutionError("Channel reference cannot be empty")

    # Case 1: #channel-name (look up by name)
    if channel_ref.startswith('#'):
        channel_name = channel_ref[1:]  # Strip # prefix
        if not channel_name:
            raise ChannelResolutionError("Channel name cannot be empty after #")

        channel = get_channel_by_name(db, channel_name)
        if channel is None:
            raise ChannelResolutionError(
                f"Channel '#{channel_name}' not found. "
                f"Use 'msgr channels' to list available channels."
            )

        return channel.id

    # Case 2: @worker-id (find or create DM channel)
    elif channel_ref.startswith('@'):
        target_worker_id = channel_ref[1:]  # Strip @ prefix
        if not target_worker_id:
            raise ChannelResolutionError("Worker ID cannot be empty after @")

        # Verify target worker exists
        target_worker = get_worker(db, target_worker_id)
        if target_worker is None:
            raise ChannelResolutionError(
                f"Worker '@{target_worker_id}' not found. "
                f"Check worker ID and try again."
            )

        # Cannot DM yourself
        if target_worker_id == current_worker_id:
            raise ChannelResolutionError("Cannot send direct message to yourself")

        # Get or create DM channel
        try:
            channel = get_or_create_direct_channel(
                db,
                current_worker_id,
                target_worker_id,
            )
            return channel.id
        except Exception as e:
            raise ChannelResolutionError(
                f"Failed to create DM channel with @{target_worker_id}: {e}"
            )

    # Case 3: Assume it's already a channel ID
    else:
        # Verify channel exists
        channel = get_channel(db, channel_ref)
        if channel is None:
            raise ChannelResolutionError(
                f"Channel '{channel_ref}' not found. "
                f"Use #channel-name for named channels or @worker-id for DMs."
            )

        return channel.id


def format_channel_name(channel_name: str, channel_type: str) -> str:
    """Format channel name for display.

    Args:
        channel_name: Raw channel name
        channel_type: Channel type (team, topic, direct)

    Returns:
        Formatted channel name with appropriate prefix

    Examples:
        >>> format_channel_name('general', 'topic')
        '#general'
        >>> format_channel_name('dm-alice-bob', 'direct')
        '@alice↔bob'
    """
    if channel_type == "direct":
        # Extract worker IDs from dm-{id1}-{id2}
        if channel_name.startswith("dm-"):
            parts = channel_name[3:].split("-", 1)
            if len(parts) == 2:
                return f"@{parts[0]}↔{parts[1]}"
        return f"@{channel_name}"
    else:
        # Team and topic channels use # prefix
        return f"#{channel_name}"


__all__ = [
    "ChannelResolutionError",
    "resolve_channel",
    "format_channel_name",
]

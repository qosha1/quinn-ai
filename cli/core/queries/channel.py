"""Backward compatibility shim. Import from channels or messages directly."""
from .channels import *  # noqa: F401, F403
from .messages import *  # noqa: F401, F403

# Explicit re-exports so static analysis tools can resolve names.
from .channels import (
    Channel,
    create_channel,
    create_direct_channel,
    get_or_create_direct_channel,
    get_channel,
    get_channel_by_name,
    create_default_org_channels,
    can_subscribe_to_channel,
    subscribe_to_channel,
    is_subscribed_to_channel,
    unsubscribe_from_channel,
    get_channel_subscribers,
    get_worker_channels,
    unsubscribe_from_all_channels,
)
from .messages import (
    Message,
    ChannelAccessError,
    create_message,
    create_message_with_notifications,
    get_message,
    get_channel_messages,
    get_thread_messages,
    search_messages,
    add_message_ref,
    get_message_refs,
)

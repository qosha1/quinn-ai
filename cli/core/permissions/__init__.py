"""Permission enforcement for QuinnAI CLI.

Two subsystems:
- access_control: Hierarchical PermissionLevel system for bead/channel CRUD access
- capabilities: Named capability system for role-based permissions like "can_hire"

All public names are re-exported here for backward compatibility.
"""

from .access_control import (
    PermissionLevel,
    PermissionDenied,
    check_channel_permission,
    check_bead_permission,
    require_channel_permission,
    require_bead_permission,
    can_worker_access_channel,
    can_worker_access_bead,
    requires_permission,
    requires_bead_permission,
    requires_channel_permission,
)
from .capabilities import (
    NamedPermissionDenied,
    check_worker_named_permission,
    check_worker_named_permissions,
    requires_named_permission,
    _get_role_permissions,
)

__all__ = [
    # access_control
    "PermissionLevel",
    "PermissionDenied",
    "check_channel_permission",
    "check_bead_permission",
    "require_channel_permission",
    "require_bead_permission",
    "can_worker_access_channel",
    "can_worker_access_bead",
    "requires_permission",
    "requires_bead_permission",
    "requires_channel_permission",
    # capabilities
    "NamedPermissionDenied",
    "check_worker_named_permission",
    "check_worker_named_permissions",
    "requires_named_permission",
    "_get_role_permissions",
]

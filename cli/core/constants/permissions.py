"""Permission level names and BD command permission constants."""

# ===================
# PERMISSIONS
# ===================

# Permission levels (0-5)
PERM_LEVEL_NONE = 0
"""No access."""

PERM_LEVEL_READ = 1
"""Can read/view."""

PERM_LEVEL_COMMENT = 2
"""Can read and comment."""

PERM_LEVEL_WRITE = 3
"""Can create and update."""

PERM_LEVEL_APPROVE = 4
"""Can approve/close work."""

PERM_LEVEL_ADMIN = 5
"""Full administrative access."""

# Permission level names for display
PERM_LEVEL_NAMES = {
    PERM_LEVEL_NONE: "none",
    PERM_LEVEL_READ: "read",
    PERM_LEVEL_COMMENT: "comment",
    PERM_LEVEL_WRITE: "write",
    PERM_LEVEL_APPROVE: "approve",
    PERM_LEVEL_ADMIN: "admin",
}

# Required permission level for bd commands
BD_COMMAND_PERMISSIONS = {
    # Read operations
    "list": PERM_LEVEL_READ,
    "show": PERM_LEVEL_READ,
    "ready": PERM_LEVEL_READ,
    "stats": PERM_LEVEL_READ,
    "blocked": PERM_LEVEL_READ,
    "doctor": PERM_LEVEL_READ,
    "sync": PERM_LEVEL_READ,
    # Write operations
    "create": PERM_LEVEL_WRITE,
    "update": PERM_LEVEL_WRITE,
    "close": PERM_LEVEL_WRITE,
    "dep": PERM_LEVEL_WRITE,
    # Admin operations
    "delete": PERM_LEVEL_ADMIN,
    "prime": PERM_LEVEL_ADMIN,
}

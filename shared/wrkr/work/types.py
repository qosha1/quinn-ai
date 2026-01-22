"""
Beads type constants for wrkr integration.

Centralizes all beads issue type strings to ensure consistency
and enable IDE autocomplete.
"""


class BeadsType:
    """Issue type constants for beads."""

    # Core work types
    TASK = "task"
    BUG = "bug"
    FEATURE = "feature"
    EPIC = "epic"

    # Org-chart types
    WORKER = "worker"
    TEAM = "team"

    # Work tracking types
    ASK = "ask"
    OKR = "okr"
    EXECUTION = "execution"

    # Escalation types
    ESCALATION = "escalation"
    BOARD_ESCALATION = "board-escalation"
    REPORT = "report"

    # Communication types
    MESSAGE = "message"
    NOTIFICATION = "notification"


class BeadsStatus:
    """Issue status constants."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    BLOCKED = "blocked"


class BeadsPriority:
    """Priority level constants (0=critical, 4=backlog)."""

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKLOG = 4


class BeadsDependency:
    """Dependency type constants."""

    DEPENDS_ON = "depends-on"
    BLOCKS = "blocks"
    SPAWNED_FROM = "spawned-from"
    SERVES = "serves"
    RELATES_TO = "relates-to"
    CAUSED_BY = "caused-by"

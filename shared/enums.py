"""
Categorical value enums for QuinnAI.

All string-based categorical values should be defined here as enums
to enable type safety and exhaustiveness checking.
"""

from enum import Enum, auto


class OrgStatus(str, Enum):
    """Organization lifecycle states."""
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"


class WorkerLifecycleStatus(str, Enum):
    """Worker lifecycle states."""
    PENDING = "pending"
    ACTIVE = "active"
    ONBOARDING = "onboarding"
    OFFBOARDING = "offboarding"
    TERMINATED = "terminated"


class WorkerRole(str, Enum):
    """Worker organizational roles."""
    CEO = "ceo"
    DIRECTOR = "director"
    MANAGER = "manager"
    SENIOR = "senior"
    WORKER = "worker"


class TeamRole(str, Enum):
    """Team membership roles."""
    ADMIN = "admin"
    LEAD = "lead"
    MEMBER = "member"


class ChannelType(str, Enum):
    """Communication channel types."""
    TOPIC = "topic"
    TEAM = "team"
    DIRECT = "direct"


class BeadType(str, Enum):
    """Bead/issue types."""
    TASK = "task"
    BUG = "bug"
    FEATURE = "feature"
    EPIC = "epic"
    ASK = "ask"


class BeadStatus(str, Enum):
    """Bead lifecycle status."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    CLOSED = "closed"


class Priority(str, Enum):
    """Issue priority levels."""
    P0 = "P0"  # Critical
    P1 = "P1"  # High
    P2 = "P2"  # Medium
    P3 = "P3"  # Low
    P4 = "P4"  # Backlog

    @classmethod
    def from_int(cls, value: int) -> "Priority":
        """Convert integer 0-4 to Priority."""
        return cls(f"P{value}")

    def to_int(self) -> int:
        """Convert Priority to integer 0-4."""
        return int(self.value[1])


class Permission(str, Enum):
    """Authorization permission types."""
    HIRE = "hire"
    FIRE = "fire"
    DELEGATE_BUDGET = "delegate_budget"
    ESCALATE = "escalate"
    APPROVE = "approve"
    ASSIGN = "assign"
    CREATE_TEAM = "create_team"
    DELETE_TEAM = "delete_team"
    MANAGE_OKR = "manage_okr"


class ResourceType(str, Enum):
    """Resource types for permission checks."""
    BEAD = "bead"
    CHANNEL = "channel"
    WORKER = "worker"
    TEAM = "team"
    OKR = "okr"


class DependencyType(str, Enum):
    """Bead dependency relationship types."""
    DEPENDS_ON = "depends-on"
    BLOCKS = "blocks"
    RELATED_TO = "related-to"


class TaskSource(str, Enum):
    """Source of work items."""
    QUEUE = "queue"
    BEADS = "beads"
    ESCALATION = "escalation"
    ASK = "ask"


class TimeSensitivity(str, Enum):
    """Message time sensitivity levels."""
    IMMEDIATE = "immediate"
    HOURS = "hours"
    DAY = "day"
    WHENEVER = "whenever"


class MessageType(str, Enum):
    """Message content types."""
    INFORM = "inform"
    REQUEST = "request"
    RESPONSE = "response"
    ESCALATION = "escalation"


class SessionState(str, Enum):
    """Session runtime states."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    CRASHED = "crashed"


class IdleBehavior(str, Enum):
    """Worker idle behavior options."""
    EXIT = "exit"
    WAIT = "wait"
    POLL = "poll"


class OutputFormat(str, Enum):
    """CLI output format options."""
    JSON = "json"
    TABLE = "table"
    TEXT = "text"
    YAML = "yaml"

"""
Work management module for wrkr.

Provides:
- BdClient: Shared client for bd CLI interactions (re-exported from shared.bd)
- BeadsQueue: QueueInterface implementation backed by beads issues
- BeadsMemory: MemoryInterface implementation with beads persistence
- LinkManager: Ask/OKR relationship management
- BeadsType/BeadsStatus/BeadsPriority: Type constants

These enable workers to:
- Pull tasks from beads (assigned issues)
- Store execution history in beads
- Track work dimensions (Ask origin, OKR alignment)
"""

from shared.bd import (
    BdClient,
    BdCommandError,
    BdError,
    BdNotFoundError,
    BdParseError,
    BdResult,
)
from shared.wrkr.work.types import (
    BeadsDependency,
    BeadsPriority,
    BeadsStatus,
    BeadsType,
)
from shared.wrkr.work.queue import (
    BeadsQueue,
    InMemoryBeadsQueue,
)
from shared.wrkr.work.memory import (
    BeadsMemory,
    InMemoryBeadsMemory,
)
from shared.wrkr.work.links import (
    Ask,
    InMemoryLinkManager,
    LinkManager,
    OKR,
    WorkLink,
)

__all__ = [
    # Client
    "BdClient",
    "BdCommandError",
    "BdError",
    "BdNotFoundError",
    "BdParseError",
    "BdResult",
    # Types
    "BeadsDependency",
    "BeadsPriority",
    "BeadsStatus",
    "BeadsType",
    # Queue
    "BeadsQueue",
    "InMemoryBeadsQueue",
    # Memory
    "BeadsMemory",
    "InMemoryBeadsMemory",
    # Links
    "Ask",
    "InMemoryLinkManager",
    "LinkManager",
    "OKR",
    "WorkLink",
]

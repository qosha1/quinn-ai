"""
Beads integration module for wrkr.

Provides:
- BeadsQueue: QueueInterface implementation backed by beads issues
- BeadsMemory: MemoryInterface implementation with beads persistence
- LinkManager: Ask/OKR relationship management

These enable workers to:
- Pull tasks from beads (assigned issues)
- Store execution history in beads
- Track work dimensions (Ask origin, OKR alignment)
"""

from shared.wrkr.beads.queue import (
    BeadsQueue,
    InMemoryBeadsQueue,
)
from shared.wrkr.beads.memory import (
    BeadsMemory,
    InMemoryBeadsMemory,
)
from shared.wrkr.beads.links import (
    Ask,
    InMemoryLinkManager,
    LinkManager,
    OKR,
    WorkLink,
)

__all__ = [
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

"""
Org-chart integration module for wrkr.

Provides:
- OrgWorker: Extended worker information from org-chart
- BeadsOrgLoader: Load org topology from beads
- OrgEscalation: Escalation through org hierarchy
- BoardNotifier: Board escalation notifications

These enable:
- Workers to escalate through their management chain
- Board notifications for human oversight
- Org-chart-based routing decisions
"""

from shared.org.topology import (
    BeadsOrgLoader,
    InMemoryOrgLoader,
    OrgWorker,
    build_standard_topology,
)
from shared.org.escalation import (
    BoardEscalation,
    BoardNotifier,
    InMemoryBoardEscalation,
    InMemoryOrgEscalation,
    OrgEscalation,
)

__all__ = [
    # Topology
    "BeadsOrgLoader",
    "InMemoryOrgLoader",
    "OrgWorker",
    "build_standard_topology",
    # Escalation
    "BoardEscalation",
    "BoardNotifier",
    "InMemoryBoardEscalation",
    "InMemoryOrgEscalation",
    "OrgEscalation",
]

"""
Escalation system for worker-to-supervisor communication.

This module provides interfaces and implementations for:
- Escalation protocols (EscalationInterface)
- Hierarchical routing (HierarchicalRouter, OrgTopology)
- Escalation management (EscalationManager)
"""

from shared.escalation.interface import (
    EscalationInterface,
    EscalationResponse,
    MockEscalation,
    NoopEscalation,
)
from shared.escalation.hierarchical import (
    HierarchicalRouter,
    OrgTopology,
    WorkerNode,
    create_simple_topology,
)
from shared.escalation.manager import (
    EscalationConfig,
    EscalationEntry,
    EscalationHistoryEntry,
    EscalationManager,
    EscalationState,
    InMemoryNotificationHandler,
    NotificationHandler,
)

__all__ = [
    # Interface
    "EscalationInterface",
    "EscalationResponse",
    "MockEscalation",
    "NoopEscalation",
    # Hierarchical routing
    "HierarchicalRouter",
    "OrgTopology",
    "WorkerNode",
    "create_simple_topology",
    # Manager
    "EscalationConfig",
    "EscalationEntry",
    "EscalationHistoryEntry",
    "EscalationManager",
    "EscalationState",
    "InMemoryNotificationHandler",
    "NotificationHandler",
]

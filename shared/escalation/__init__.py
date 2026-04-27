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
from shared.escalation.config import EscalationConfig
from shared.escalation.manager import EscalationManager
from shared.escalation.types import (
    AutoEscalationSettings,
    BoardInterventionSettings,
    EscalationEntry,
    EscalationHistoryEntry,
    EscalationPathLevel,
    EscalationState,
    InMemoryNotificationHandler,
    NotificationHandler,
    NotificationSettings,
    RetryPolicy,
    TimeoutWarningSettings,
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
    # Config types
    "AutoEscalationSettings",
    "BoardInterventionSettings",
    "EscalationPathLevel",
    "NotificationSettings",
    "RetryPolicy",
    "TimeoutWarningSettings",
]

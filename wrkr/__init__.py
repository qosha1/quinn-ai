"""QuinnAI Worker - Pure state machine abstraction.

This module provides the worker abstraction layer for QuinnAI.
Workers are provider-agnostic state machines that:
- Transition through defined states (pending -> onboarding -> active -> ...)
- Execute tasks via abstract interface (subclass implements provider logic)
- Use pluggable queue, memory, and escalation interfaces

NO provider dependencies (Claude, OpenAI, etc.) belong here.
Provider integration happens in the session/provider layer above.
"""

from .core.state import WorkerState, can_transition, transition, InvalidTransition
from .core.task import Task
from .core.result import WorkerResult
from .core.config import WorkerConfig
from .core.worker import BaseWorker
from .queue.interface import QueueInterface, MockQueue
from .memory.interface import MemoryInterface, MockMemory
from .escalation.interface import (
    EscalationInterface,
    EscalationResponse,
    MockEscalation,
    NoopEscalation,
)
from .escalation.hierarchical import (
    OrgTopology,
    WorkerNode,
    HierarchicalRouter,
    create_simple_topology,
)

__all__ = [
    # Core state machine
    "WorkerState",
    "can_transition",
    "transition",
    "InvalidTransition",
    # Task and result
    "Task",
    "WorkerResult",
    # Configuration
    "WorkerConfig",
    # Base worker
    "BaseWorker",
    # Interfaces (protocols)
    "QueueInterface",
    "MemoryInterface",
    "EscalationInterface",
    "EscalationResponse",
    # Mock implementations for testing
    "MockQueue",
    "MockMemory",
    "MockEscalation",
    "NoopEscalation",
    # Hierarchical escalation
    "OrgTopology",
    "WorkerNode",
    "HierarchicalRouter",
    "create_simple_topology",
]

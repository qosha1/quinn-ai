"""QuinnAI Worker - Pure state machine abstraction.

This module provides the worker abstraction layer for QuinnAI.
Workers are provider-agnostic state machines that:
- Transition through defined states (pending -> onboarding -> active -> ...)
- Execute tasks via abstract interface (subclass implements provider logic)
- Use pluggable queue, memory, and escalation interfaces

NO provider dependencies (Claude, OpenAI, etc.) belong here.
Provider integration happens in the session/provider layer above.

Type Layers:
- Execution layer (this module): WorkerConfig, WorkerResult, WorkerNode
  Optimized for state machine execution with idle_behavior, escalation, etc.
- Organizational layer (shared.core): CoreWorkerConfig, CoreWorkerResult, CoreWorkerNode
  Full organizational types with team_id, hiring_authority, direct_reports, etc.

Both layers are available via imports for cross-layer compatibility.
"""

from shared.wrkr.core.state import WorkerState, can_transition, transition, InvalidTransition
from shared.wrkr.core.task import Task
from shared.wrkr.core.result import WorkerResult
from shared.wrkr.core.config import WorkerConfig
from shared.wrkr.core.worker import BaseWorker
from shared.queue.interface import QueueInterface, MockQueue
from shared.wrkr.memory.interface import MemoryInterface, MockMemory
from shared.escalation.interface import (
    EscalationInterface,
    EscalationResponse,
    MockEscalation,
    NoopEscalation,
)
from shared.escalation.hierarchical import (
    OrgTopology,
    WorkerNode,
    HierarchicalRouter,
    create_simple_topology,
)

# Re-export canonical types from shared.core for cross-layer compatibility
from shared.core.worker import (
    WorkerConfig as CoreWorkerConfig,
    WorkerInfo,
    WorkerResult as CoreWorkerResult,
    WorkerNode as CoreWorkerNode,
)

__all__ = [
    # Core state machine
    "WorkerState",
    "can_transition",
    "transition",
    "InvalidTransition",
    # Task and result (execution layer)
    "Task",
    "WorkerResult",
    # Configuration (execution layer)
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
    # Canonical types from shared.core (organizational layer)
    "CoreWorkerConfig",
    "WorkerInfo",
    "CoreWorkerResult",
    "CoreWorkerNode",
]

"""
Canonical data structures for QuinnAI.

This module provides the single source of truth for core types used
throughout the QuinnAI system. All other modules should import from here.

Per CLAUDE.md principles:
- "Every Agent Is A Worker" - WorkerConfig, WorkerInfo, WorkerNode
- "Session = Worker's Brain" - SessionConfig, SessionId, SessionState
- "One Protocol For Everything" - Message, WorkerMessage, Notification

Usage:
    from shared.core import (
        # States
        WorkerState,
        SessionState,
        worker_state_to_session,
        session_state_to_worker,

        # Worker types
        WorkerConfig,
        WorkerInfo,
        WorkerResult,
        WorkerNode,

        # Session types
        SessionConfig,
        SessionId,
        SessionMetrics,
        SessionOutput,

        # Message types
        Message,
        WorkerMessage,
        Notification,
        MessageRole,
        MessageType,
        TimeSensitivity,
    )
"""

# State definitions (canonical source)
from .state import (
    # Enums
    WorkerState,
    SessionState,
    # Transitions
    WORKER_STATE_TRANSITIONS,
    SESSION_STATE_TRANSITIONS,
    InvalidStateTransition,
    can_transition_worker,
    can_transition_session,
    transition_worker,
    transition_session,
    # Mapping
    WORKER_TO_SESSION_STATE,
    SESSION_TO_WORKER_STATE,
    worker_state_to_session,
    session_state_to_worker,
    is_worker_awake,
    is_worker_responsive,
)

# Worker types
from .worker import (
    WorkerConfig,
    WorkerInfo,
    WorkerResult,
    WorkerNode,
)

# Session types
from .session import (
    SessionId,
    SessionConfig,
    SessionMetrics,
    SessionOutput,
    PromptResult,
    ExtractedOutput,
)

# Message types
from .message import (
    # Enums
    MessageRole,
    MessageType,
    TimeSensitivity,
    # Classes
    Message,
    WorkerMessage,
    Notification,
    ConversationMessage,
    ToolCall,
    ToolResult,
)

__all__ = [
    # State enums
    "WorkerState",
    "SessionState",
    # State transitions
    "WORKER_STATE_TRANSITIONS",
    "SESSION_STATE_TRANSITIONS",
    "InvalidStateTransition",
    "can_transition_worker",
    "can_transition_session",
    "transition_worker",
    "transition_session",
    # State mapping
    "WORKER_TO_SESSION_STATE",
    "SESSION_TO_WORKER_STATE",
    "worker_state_to_session",
    "session_state_to_worker",
    "is_worker_awake",
    "is_worker_responsive",
    # Worker types
    "WorkerConfig",
    "WorkerInfo",
    "WorkerResult",
    "WorkerNode",
    # Session types
    "SessionId",
    "SessionConfig",
    "SessionMetrics",
    "SessionOutput",
    "PromptResult",
    "ExtractedOutput",
    # Message enums
    "MessageRole",
    "MessageType",
    "TimeSensitivity",
    # Message types
    "Message",
    "WorkerMessage",
    "Notification",
    "ConversationMessage",
    "ToolCall",
    "ToolResult",
]

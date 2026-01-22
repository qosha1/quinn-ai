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
        WorkState,
        worker_state_to_session,
        session_state_to_worker,
        can_transition_work,
        transition_work,

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
    WorkState,
    # Transitions
    WORKER_STATE_TRANSITIONS,
    SESSION_STATE_TRANSITIONS,
    WORK_STATE_TRANSITIONS,
    InvalidStateTransition,
    can_transition_worker,
    can_transition_session,
    can_transition_work,
    transition_worker,
    transition_session,
    transition_work,
    # Mapping
    WORKER_TO_SESSION_STATE,
    SESSION_TO_WORKER_STATE,
    worker_state_to_session,
    session_state_to_worker,
    is_worker_awake,
    is_worker_responsive,
    # Work state helpers
    is_work_terminal,
    is_work_active,
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
    "WorkState",
    # State transitions
    "WORKER_STATE_TRANSITIONS",
    "SESSION_STATE_TRANSITIONS",
    "WORK_STATE_TRANSITIONS",
    "InvalidStateTransition",
    "can_transition_worker",
    "can_transition_session",
    "can_transition_work",
    "transition_worker",
    "transition_session",
    "transition_work",
    # State mapping
    "WORKER_TO_SESSION_STATE",
    "SESSION_TO_WORKER_STATE",
    "worker_state_to_session",
    "session_state_to_worker",
    "is_worker_awake",
    "is_worker_responsive",
    # Work state helpers
    "is_work_terminal",
    "is_work_active",
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

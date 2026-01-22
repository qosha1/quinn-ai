"""
Session integration for wrkr.

Provides SessionWorker that executes tasks through pyterm AI sessions,
bridging the provider-agnostic wrkr state machine to actual AI execution.
"""

from shared.wrkr.session.adapter import (
    PromptBuilder,
    DefaultPromptBuilder,
    ResultExtractor,
)
from shared.wrkr.session.worker import (
    SessionFactory,
    SessionWorker,
    TimeoutError,
    create_session_worker,
)

__all__ = [
    # Adapters
    "PromptBuilder",
    "DefaultPromptBuilder",
    "ResultExtractor",
    # Worker
    "SessionFactory",
    "SessionWorker",
    "TimeoutError",
    "create_session_worker",
]

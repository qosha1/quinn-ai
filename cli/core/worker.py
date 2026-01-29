"""
Worker state machine implementation - backward compatibility module.

This module maintains backward compatibility by re-exporting all classes
and functions from the refactored worker package.

The actual implementation has been split into focused modules:
- worker/base.py: Main Worker class
- worker/storage_manager.py: Storage operations
- worker/budget_manager.py: Budget management
- worker/hiring.py: Hiring operations
- worker/delegation.py: Delegation management
- worker/lifecycle_manager.py: Lifecycle transitions
- worker/session_manager.py: Session management
- worker_cleanup.py: Cleanup functions
"""

# Re-export everything from the worker package
from .worker import (
    Worker,
    HiringScope,
    HiringError,
    InsufficientHiringAuthority,
    MaxReportsExceeded,
    check_offboarding_ask_completed,
    process_offboarding_cleanup,
    cleanup_terminated_worker,
)

# Re-export BdClient for test compatibility
from shared.bd.client import BdClient, BdCommandError

__all__ = [
    "Worker",
    "HiringScope",
    "HiringError",
    "InsufficientHiringAuthority",
    "MaxReportsExceeded",
    "check_offboarding_ask_completed",
    "process_offboarding_cleanup",
    "cleanup_terminated_worker",
    "BdClient",
    "BdCommandError",
]

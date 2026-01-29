"""
Worker package - refactored into focused modules.

This package provides the Worker class and related components split
across multiple modules following the Single Responsibility Principle.

Main exports:
- Worker: Main worker class (composes all managers)
- HiringScope: Hiring authority definition
- Exceptions: HiringError, InsufficientHiringAuthority, MaxReportsExceeded

Internal modules (not typically imported directly):
- base: Worker base class
- storage_manager: Storage operations
- budget_manager: Budget management
- hiring: Hiring operations
- delegation: Delegation management
- lifecycle_manager: Lifecycle transitions
- session_manager: Session management
"""

# Re-export main Worker class for backward compatibility
from .base import Worker

# Re-export hiring-related classes
from .hiring import (
    HiringScope,
    HiringError,
    InsufficientHiringAuthority,
    MaxReportsExceeded,
)

# Re-export cleanup functions from the old worker module
# These will remain in the original worker.py file as standalone functions
from ..worker_cleanup import (
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

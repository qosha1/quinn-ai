"""
Interface definitions for board UI components.

Following interface-first design: design interfaces as true contracts.
Even with one implementation, build for many.
"""

from .terminal import TerminalProvider, WindowHandle
from .org_connection import OrgConnection, OrgInfo, WorkerInfo

__all__ = [
    "TerminalProvider",
    "WindowHandle",
    "OrgConnection",
    "OrgInfo",
    "WorkerInfo",
]

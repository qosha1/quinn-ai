"""
Beads (bd) client for subprocess calls.

Provides a shared client for calling the bd CLI tool.
"""

from .client import BdClient, BdClientError

__all__ = ["BdClient", "BdClientError"]

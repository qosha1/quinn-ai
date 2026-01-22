"""
Process adapters for external system interactions.

Provides abstraction layers for subprocess calls, tmux, and git operations,
enabling easier testing and implementation swapping.
"""

from .process import ProcessAdapter, ProcessResult, SubprocessAdapter
from .tmux import TmuxAdapter, TmuxSession
from .git import GitAdapter, GitStatus
from .beads import BeadsClient, SubprocessBeadsClient, MockBeadsClient, Bead, BeadResult

__all__ = [
    # Process
    "ProcessAdapter",
    "ProcessResult",
    "SubprocessAdapter",
    # Tmux
    "TmuxAdapter",
    "TmuxSession",
    # Git
    "GitAdapter",
    "GitStatus",
    # Beads
    "BeadsClient",
    "SubprocessBeadsClient",
    "MockBeadsClient",
    "Bead",
    "BeadResult",
]

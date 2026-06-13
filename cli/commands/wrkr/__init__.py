"""
Worker operation commands.
"""

from .get_work import get_work_cmd
from .search import search_cmd
from .status import status_cmd
from .delegate import delegate_cmd
from .report import report_cmd
from .cleanup import cleanup_cmd
from .restart import restart_cmd
from .exec import exec_cmd
from .inspect import inspect_cmd
from .pause import pause_cmd, resume_cmd
from .ship import ship_cmd

__all__ = [
    "get_work_cmd",
    "search_cmd",
    "status_cmd",
    "delegate_cmd",
    "report_cmd",
    "cleanup_cmd",
    "restart_cmd",
    "exec_cmd",
    "inspect_cmd",
    "pause_cmd",
    "resume_cmd",
    "ship_cmd",
]

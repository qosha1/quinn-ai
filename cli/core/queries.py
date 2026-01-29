"""
Query helpers for common database operations.

This module provides high-level functions for interacting with quinn.db
without writing raw SQL. All functions are organized by entity type.

IMPORTANT: This file is a backward-compatibility facade. The actual
implementations have been split into focused modules in cli/core/queries/.
All imports are re-exported here to maintain existing import paths.
"""

# Re-export everything from submodules for backward compatibility
from .queries.common import *
from .queries.config import *
from .queries.org import *
from .queries.team import *
from .queries.worker import *
from .queries.channel import *
from .queries.budget import *
from .queries.okr import *
from .queries.permission import *
from .queries.delegation import *

# Import __all__ from each module to build comprehensive export list
from .queries.common import __all__ as _common_all
from .queries.config import __all__ as _config_all
from .queries.org import __all__ as _org_all
from .queries.team import __all__ as _team_all
from .queries.worker import __all__ as _worker_all
from .queries.channel import __all__ as _channel_all
from .queries.budget import __all__ as _budget_all
from .queries.okr import __all__ as _okr_all
from .queries.permission import __all__ as _permission_all
from .queries.delegation import __all__ as _delegation_all

__all__ = (
    _common_all +
    _config_all +
    _org_all +
    _team_all +
    _worker_all +
    _channel_all +
    _budget_all +
    _okr_all +
    _permission_all +
    _delegation_all
)

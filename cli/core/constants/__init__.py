"""
QuinnAI CLI constants.

Central location for all magic values, following the 'No Magic Values' principle.
All default values that are used in multiple places should be defined here.

Sub-modules:
- timing: timeouts, polling intervals, state monitoring
- budget: skill thresholds, worker costs, budget, delegation
- messaging: notifications, escalation, activity signals, continuation engine
- beads: bead types, entity types, reference types, lifecycle states, OKR constants
- permissions: permission levels, BD command permissions
- system: IDs, names, pagination, database, terminal, logging, stop controller
"""

from .timing import *  # noqa: F401, F403
from .budget import *  # noqa: F401, F403
from .messaging import *  # noqa: F401, F403
from .beads import *  # noqa: F401, F403
from .permissions import *  # noqa: F401, F403
from .system import *  # noqa: F401, F403


# ===================
# UTILITY FUNCTIONS
# ===================

def ms_to_seconds(ms: int) -> float:
    """Convert milliseconds to seconds.

    Args:
        ms: Time in milliseconds

    Returns:
        Time in seconds as a float
    """
    return ms / 1000.0

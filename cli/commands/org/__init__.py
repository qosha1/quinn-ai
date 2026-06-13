"""
Organization management commands.
"""

from .init import init_cmd
from .apply import apply_cmd
from .start import start_cmd
from .stop import stop_cmd
from .restart import restart_cmd
from .status import status_cmd
from .cleanup import cleanup_cmd
from .logs import logs_cmd
from .observe import observe_cmd
from .okr import okr_cmd
from .budget import budget_cmd
from .chart import chart_cmd
from .hire import hire_cmd
from .hire_team import hire_team_cmd, templates_cmd
from .fire import fire_cmd
from .delegate_authority import delegate_authority_cmd
from .revoke_authority import revoke_authority_cmd
from .promote import promote_cmd
from .demote import demote_cmd
from .delegations import delegations_cmd
from .provider import provider_cmd
from .watch import watch
from .ps import ps_cmd
from .broadcast import broadcast_cmd
from .gc import gc_cmd
from .snapshot import snapshot_cmd
from .audit import audit_cmd
from .env import env_cmd
from .tail import tail_cmd
from cli.core.rules.cli import rules_cmd

__all__ = [
    "init_cmd",
    "apply_cmd",
    "start_cmd",
    "stop_cmd",
    "restart_cmd",
    "status_cmd",
    "cleanup_cmd",
    "logs_cmd",
    "observe_cmd",
    "okr_cmd",
    "budget_cmd",
    "chart_cmd",
    "hire_cmd",
    "hire_team_cmd",
    "templates_cmd",
    "fire_cmd",
    "delegate_authority_cmd",
    "revoke_authority_cmd",
    "promote_cmd",
    "demote_cmd",
    "delegations_cmd",
    "provider_cmd",
    "watch",
    "ps_cmd",
    "broadcast_cmd",
    "gc_cmd",
    "snapshot_cmd",
    "audit_cmd",
    "env_cmd",
    "tail_cmd",
    "rules_cmd",
]

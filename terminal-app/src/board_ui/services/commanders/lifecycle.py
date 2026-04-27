"""Org-level lifecycle commands: start, stop, restart."""

from ...interfaces.org_connection import OrgStatus
from ...logging_config import get_board_logger
from ..qn_cli_client import get_default_qn_cli
from ._context import OrgContext

logger = get_board_logger(__name__)


class LifecycleCommander:
    """Start, stop, and restart the org via the qn CLI."""

    def __init__(self, ctx: OrgContext) -> None:
        self._ctx = ctx

    def start_org(self) -> bool:
        """Start the org if it's stopped or initialized."""
        org_info = self._ctx.get_org_info()
        if org_info.status not in (OrgStatus.INITIALIZED, OrgStatus.STOPPED):
            return False

        from ..org_discovery import start_org as subprocess_start_org

        return subprocess_start_org(self._ctx.org_path).success

    def stop_org(self) -> bool:
        """Stop the org gracefully if it's running."""
        org_info = self._ctx.get_org_info()
        if org_info.status != OrgStatus.RUNNING:
            return False

        from ..org_discovery import stop_org as subprocess_stop_org

        return subprocess_stop_org(self._ctx.org_path).success

    def restart_org(self) -> tuple[bool, str]:
        """Restart the org (stop then start)."""
        org_info = self._ctx.get_org_info()
        if org_info.status not in (OrgStatus.RUNNING, OrgStatus.STOPPED):
            return False, f"Cannot restart org in status: {org_info.status.value}"

        result = get_default_qn_cli().org_restart(self._ctx.org_path)
        if result.success:
            return True, "Organization restarted successfully"
        return False, result.error_message

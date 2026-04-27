"""Org-level lifecycle commands: start, stop, restart."""

import subprocess

from ...interfaces.org_connection import OrgStatus
from ...logging_config import get_board_logger
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

        from ..org_discovery import _get_qn_command

        cmd = _get_qn_command() + [
            "--org-path", str(self._ctx.org_path),
            "org", "restart",
            "--skip-config-validation",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self._ctx.org_path),
            )
            if result.returncode == 0:
                return True, "Organization restarted successfully"
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            return False, error_msg or f"Restart failed with code {result.returncode}"
        except subprocess.TimeoutExpired:
            return False, "Restart timed out after 60 seconds"
        except Exception as e:
            return False, f"Failed to run restart command: {e}"

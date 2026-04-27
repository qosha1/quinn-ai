"""Org command execution service.

Thin wrapper for `qn org start/stop/restart` that returns (bool, message)
tuples — the contract older callers in views/* depend on. Delegates the
actual subprocess work to QnCliClient.
"""

from pathlib import Path

from ..logging_config import get_board_logger
from .qn_cli_client import get_default_qn_cli

logger = get_board_logger(__name__)


class OrgCommandError(Exception):
    """Base exception for org command errors."""

    pass


class OrgCommandService:
    """Service for executing org lifecycle commands."""

    def __init__(self, org_path: Path):
        self.org_path = org_path

    def start_org(self, spawn_ceo: bool = True) -> tuple[bool, str]:
        """Start the org. Returns (success, human-readable message)."""
        client = get_default_qn_cli()
        logger.info(f"Starting org via qn at {self.org_path}")
        result = client.org_start(self.org_path, spawn_ceo=spawn_ceo)
        if result.success:
            logger.info(f"Org started successfully: {self.org_path}")
            return True, "Organization started successfully"
        logger.error(f"Failed to start org: {result.error_message}")
        return False, f"Failed to start: {result.error_message}"

    def stop_org(self, graceful_timeout: int = 30) -> tuple[bool, str]:
        """Stop the org. Returns (success, human-readable message)."""
        client = get_default_qn_cli()
        logger.info(f"Stopping org via qn at {self.org_path}")
        # Subprocess timeout = graceful + buffer so the qn process has room
        # to wind down before we kill it.
        result = client.run(
            ["--org-path", str(self.org_path), "org", "stop",
             f"--graceful-timeout={graceful_timeout}"],
            timeout=graceful_timeout + 10,
        )
        if result.success:
            logger.info(f"Org stopped successfully: {self.org_path}")
            return True, "Organization stopped successfully"
        logger.error(f"Failed to stop org: {result.error_message}")
        return False, f"Failed to stop: {result.error_message}"

    def restart_org(self) -> tuple[bool, str]:
        """Restart the org. Returns (success, human-readable message)."""
        client = get_default_qn_cli()
        logger.info(f"Restarting org via qn at {self.org_path}")
        # restart_org default skips config validation; this caller wants the
        # full validation flow, so call run() directly.
        result = client.run(
            ["--org-path", str(self.org_path), "org", "restart"],
            timeout=60,
        )
        if result.success:
            logger.info(f"Org restarted successfully: {self.org_path}")
            return True, "Organization restarted successfully"
        logger.error(f"Failed to restart org: {result.error_message}")
        return False, f"Failed to restart: {result.error_message}"

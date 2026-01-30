"""
Org command execution service.

Provides methods to execute qn org commands (start, stop, restart)
from the board UI.
"""

import subprocess
from pathlib import Path
from typing import Optional

from ..logging_config import get_board_logger

logger = get_board_logger(__name__)


class OrgCommandError(Exception):
    """Base exception for org command errors."""
    pass


class OrgCommandService:
    """Service for executing org lifecycle commands."""

    def __init__(self, org_path: Path):
        """Initialize org command service.

        Args:
            org_path: Path to the organization directory
        """
        self.org_path = org_path

    def start_org(self, spawn_ceo: bool = True) -> tuple[bool, str]:
        """Start the organization.

        Args:
            spawn_ceo: Whether to spawn CEO session (default: True)

        Returns:
            Tuple of (success, message)
        """
        try:
            cmd = ["qn", "--org-path", str(self.org_path), "org", "start"]
            if not spawn_ceo:
                cmd.append("--no-spawn-ceo")

            logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info(f"Org started successfully: {self.org_path}")
                return True, "Organization started successfully"
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                logger.error(f"Failed to start org: {error_msg}")
                return False, f"Failed to start: {error_msg}"

        except subprocess.TimeoutExpired:
            logger.error(f"Org start command timed out")
            return False, "Command timed out after 30 seconds"
        except Exception as e:
            logger.error(f"Error starting org: {e}")
            return False, f"Error: {str(e)}"

    def stop_org(self, graceful_timeout: int = 30) -> tuple[bool, str]:
        """Stop the organization.

        Args:
            graceful_timeout: Seconds to wait for graceful shutdown

        Returns:
            Tuple of (success, message)
        """
        try:
            cmd = [
                "qn",
                "--org-path",
                str(self.org_path),
                "org",
                "stop",
                f"--graceful-timeout={graceful_timeout}",
            ]

            logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=graceful_timeout + 10,  # Extra buffer
            )

            if result.returncode == 0:
                logger.info(f"Org stopped successfully: {self.org_path}")
                return True, "Organization stopped successfully"
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                logger.error(f"Failed to stop org: {error_msg}")
                return False, f"Failed to stop: {error_msg}"

        except subprocess.TimeoutExpired:
            logger.error(f"Org stop command timed out")
            return False, f"Command timed out after {graceful_timeout + 10} seconds"
        except Exception as e:
            logger.error(f"Error stopping org: {e}")
            return False, f"Error: {str(e)}"

    def restart_org(self) -> tuple[bool, str]:
        """Restart the organization.

        Returns:
            Tuple of (success, message)
        """
        try:
            cmd = ["qn", "--org-path", str(self.org_path), "org", "restart"]

            logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # Longer timeout for stop + start
            )

            if result.returncode == 0:
                logger.info(f"Org restarted successfully: {self.org_path}")
                return True, "Organization restarted successfully"
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                logger.error(f"Failed to restart org: {error_msg}")
                return False, f"Failed to restart: {error_msg}"

        except subprocess.TimeoutExpired:
            logger.error(f"Org restart command timed out")
            return False, "Command timed out after 60 seconds"
        except Exception as e:
            logger.error(f"Error restarting org: {e}")
            return False, f"Error: {str(e)}"

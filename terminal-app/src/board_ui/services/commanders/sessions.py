"""Worker-session-level commands: restart and stale-session cleanup."""

import subprocess
from typing import Optional

from ...logging_config import get_board_logger
from ._context import OrgContext

logger = get_board_logger(__name__)


class SessionsCommander:
    """Restart and clean up worker sessions."""

    def __init__(self, ctx: OrgContext) -> None:
        self._ctx = ctx

    def restart_worker_session(
        self,
        worker_id: str,
        force: bool = True,
    ) -> tuple[bool, Optional[str]]:
        """Restart a worker's session, spawning one if none exists.

        Returns (success, tmux_session_name).
        """
        from ..org_discovery import _get_qn_command

        cmd = _get_qn_command() + [
            "--org-path", str(self._ctx.org_path),
            "wrkr", "restart", worker_id,
        ]
        if force:
            cmd.append("--force")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self._ctx.org_path),
            )
            if result.returncode == 0:
                row = self._ctx.db.fetchone(
                    "SELECT tmux_session_name FROM sessions WHERE worker_id = ?",
                    (worker_id,),
                )
                tmux_name = row["tmux_session_name"] if row else None
                return True, tmux_name

            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            logger.error(f"Failed to restart worker {worker_id}: {error_msg}")
            return False, None

        except subprocess.TimeoutExpired:
            logger.error(f"Worker restart timed out for {worker_id}")
            return False, None
        except Exception as e:
            logger.error(f"Error restarting worker {worker_id}: {e}")
            return False, None

    def cleanup_stale_session(self, worker_id: str, tmux_session_name: Optional[str]) -> bool:
        """Mark sessions stopped in DB and unbind from the binding manager."""
        try:
            self._ctx.db.execute(
                """UPDATE sessions
                   SET tmux_session_name = NULL,
                       state = 'stopped',
                       stopped_at = CURRENT_TIMESTAMP
                   WHERE worker_id = ?""",
                (worker_id,),
            )
            self._ctx.db.connection.commit()

            self._ctx.db.execute(
                """UPDATE worker_state
                   SET runtime_status = 'stopped',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE worker_id = ?""",
                (worker_id,),
            )
            self._ctx.db.connection.commit()

            try:
                from cli.core.sessions.binding_manager import get_binding_manager

                manager = get_binding_manager(self._ctx.db)
                manager.unbind(worker_id)
            except (ImportError, Exception) as e:
                logger.debug(f"Could not unbind session for {worker_id}: {e}")

            logger.info(f"Cleaned up stale session for worker {worker_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cleanup stale session for {worker_id}: {e}")
            return False

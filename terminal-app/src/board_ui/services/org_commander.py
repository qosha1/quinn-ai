"""
Mutation and intervention operations for QuinnAI org state.

OrgCommander handles all state-changing operations: starting/stopping the org,
worker interventions, session management, briefings, and provider configuration.
Intended to be used as a delegate from QuinnAIOrgConnection.
"""

import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from ..logging_config import get_board_logger
from ..interfaces.org_connection import OrgStatus

logger = get_board_logger(__name__)


class OrgCommander:
    """All mutation and intervention operations for a QuinnAI org.

    Takes a database wrapper and org path. All methods write to the database
    or execute CLI subprocesses that transition org/worker state.

    Args:
        db: A database wrapper with fetchone/fetchall/execute/connection interface
        org_path: Resolved path to the org directory
        board_channel: Name of the board channel
        escalations_channel: Fallback channel name for backward compatibility
        get_ceo_fn: Callable that returns the current CEO WorkerInfo (or None)
        get_board_channel_id_fn: Callable that returns the board channel ID (or None)
        get_org_info_fn: Callable that returns OrgInfo
        mark_message_read_fn: Callable(message_id) to mark a message read
    """

    def __init__(
        self,
        db: Any,
        org_path: Path,
        board_channel: str,
        escalations_channel: str,
        get_ceo_fn: Callable,
        get_board_channel_id_fn: Callable,
        get_org_info_fn: Callable,
        mark_message_read_fn: Callable,
    ) -> None:
        self._db = db
        self._org_path = org_path
        self._board_channel = board_channel
        self._escalations_channel = escalations_channel
        self._get_ceo = get_ceo_fn
        self._get_board_channel_id = get_board_channel_id_fn
        self._get_org_info = get_org_info_fn
        self._mark_message_read = mark_message_read_fn

    # ==================
    # ORG LIFECYCLE
    # ==================

    def start_org(self) -> bool:
        """Start the org (if stopped or initialized)."""
        org_info = self._get_org_info()
        if org_info.status not in (OrgStatus.INITIALIZED, OrgStatus.STOPPED):
            return False

        from .org_discovery import start_org as subprocess_start_org

        result = subprocess_start_org(self._org_path)
        return result.success

    def stop_org(self) -> bool:
        """Stop the org gracefully."""
        org_info = self._get_org_info()
        if org_info.status != OrgStatus.RUNNING:
            return False

        from .org_discovery import stop_org as subprocess_stop_org

        result = subprocess_stop_org(self._org_path)
        return result.success

    def restart_org(self) -> tuple[bool, str]:
        """Restart the org (stop then start)."""
        org_info = self._get_org_info()
        if org_info.status not in (OrgStatus.RUNNING, OrgStatus.STOPPED):
            return False, f"Cannot restart org in status: {org_info.status.value}"

        from .org_discovery import _get_qn_command

        cmd = _get_qn_command() + [
            "--org-path", str(self._org_path),
            "org", "restart",
            "--skip-config-validation",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self._org_path),
            )

            if result.returncode == 0:
                return True, "Organization restarted successfully"
            else:
                error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
                return False, error_msg or f"Restart failed with code {result.returncode}"

        except subprocess.TimeoutExpired:
            return False, "Restart timed out after 60 seconds"
        except Exception as e:
            return False, f"Failed to run restart command: {e}"

    def restart_worker_session(self, worker_id: str, force: bool = True) -> tuple[bool, Optional[str]]:
        """Restart a worker's session, spawning one if none exists."""
        from .org_discovery import _get_qn_command

        cmd = _get_qn_command() + [
            "--org-path", str(self._org_path),
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
                cwd=str(self._org_path),
            )

            if result.returncode == 0:
                row = self._db.fetchone(
                    "SELECT tmux_session_name FROM sessions WHERE worker_id = ?",
                    (worker_id,),
                )
                tmux_name = row["tmux_session_name"] if row else None
                return True, tmux_name
            else:
                error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
                logger.error(f"Failed to restart worker {worker_id}: {error_msg}")
                return False, None

        except subprocess.TimeoutExpired:
            logger.error(f"Worker restart timed out for {worker_id}")
            return False, None
        except Exception as e:
            logger.error(f"Error restarting worker {worker_id}: {e}")
            return False, None

    # ==================
    # BOARD INTERVENTIONS
    # ==================

    def pause_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Pause a worker by stopping its session directly."""
        try:
            from cli.core.worker import Worker
            from shared.exceptions import WorkerNotFound
            from shared.exceptions import InvalidStateTransition

            worker = Worker.get(self._db, worker_id)
            worker.stop_session()

            self._log_intervention("pause", worker_id, reason or "Board paused worker")
            self._notify_ceo_of_intervention("pause", worker_id, reason or "Board paused worker")
            return True
        except WorkerNotFound:
            logger.error(f"Worker {worker_id} not found")
            return False
        except InvalidStateTransition as e:
            logger.error(f"Cannot pause worker {worker_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error pausing worker {worker_id}: {e}")
            return False

    def resume_worker(self, worker_id: str) -> bool:
        """Resume a paused worker by setting its runtime status to 'starting'."""
        try:
            from cli.core.queries import update_worker_runtime_status

            update_worker_runtime_status(self._db, worker_id, "starting")

            self._log_intervention("resume", worker_id, "Board resumed worker")
            self._notify_ceo_of_intervention("resume", worker_id, "Board resumed worker")
            return True
        except Exception as e:
            logger.error(f"Error resuming worker {worker_id}: {e}")
            return False

    def fire_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Terminate a worker via direct lifecycle transitions."""
        try:
            from cli.core.worker import Worker
            from shared.exceptions import WorkerNotFound, InvalidStateTransition
            from shared.enums import WorkerLifecycleStatus

            worker = Worker(self._db, worker_id, org_path=self._org_path)
            _ = worker.name  # raises WorkerNotFound if missing

            if worker.lifecycle_status == WorkerLifecycleStatus.ACTIVE.value:
                worker.start_offboarding()

            # Stop session in DB if still running (terminate() only handles in-memory sessions)
            if worker.runtime_status in ("starting", "running", "idle", "working", "blocked"):
                try:
                    worker.stop_session()
                except InvalidStateTransition:
                    pass  # Already stopped or in non-stoppable state

            worker.terminate()

            self._log_intervention("fire", worker_id, reason or "Board fired worker")
            self._notify_ceo_of_intervention("fire", worker_id, reason or "No reason provided")
            return True
        except WorkerNotFound:
            logger.error(f"Worker {worker_id} not found")
            return False
        except InvalidStateTransition as e:
            logger.error(f"Cannot fire worker {worker_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error firing worker {worker_id}: {e}")
            return False

    def _log_intervention(self, action: str, worker_id: str, reason: str) -> None:
        """Log intervention to board-channel."""
        try:
            now = datetime.now()

            channel_id = self._get_board_channel_id()
            if not channel_id:
                return

            ceo = self._get_ceo()
            if not ceo:
                logger.warning("Cannot log intervention: CEO worker not found")
                return

            message_id = f"msg-{str(uuid.uuid4())[:8]}"

            content = (
                f"**INTERVENTION: {action.upper()}**\n\n"
                f"Worker: {worker_id}\n"
                f"Reason: {reason}\n"
                f"Time: {now.isoformat()}"
            )

            self._db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, 3, 'immediate', ?)""",
                (message_id, channel_id, ceo.id, content, now),
            )
            self._db.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to log intervention: {e}")

    def _notify_ceo_of_intervention(self, action: str, worker_id: str, reason: str) -> None:
        """Notify CEO of board intervention by creating notification bead."""
        try:
            channel_id = self._get_board_channel_id()
            if not channel_id:
                return

            ceo = self._get_ceo()
            if not ceo:
                logger.warning("Cannot notify CEO: CEO worker not found")
                return

            message_id = f"msg-{str(uuid.uuid4())[:8]}"
            now = datetime.now()

            content = (
                f"**BOARD INTERVENTION NOTIFICATION**\n\n"
                f"Action: {action.upper()}\n"
                f"Worker: {worker_id}\n"
                f"Reason: {reason}\n"
                f"Time: {now.isoformat()}"
            )

            self._db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, 4, 'immediate', ?)""",
                (message_id, channel_id, ceo.id, content, now),
            )

            notification_id = f"nb-{str(uuid.uuid4())[:8]}"
            self._db.execute(
                """INSERT INTO notification_beads
                   (id, worker_id, message_id, channel_id, status, priority, created_at, read_at, expires_at)
                   VALUES (?, ?, ?, ?, 'pending', 4, ?, NULL, NULL)""",
                (notification_id, ceo.id, message_id, channel_id, now),
            )

            self._db.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to notify CEO: {e}")

    # ==================
    # BOARD RESPONSES
    # ==================

    def send_board_response(
        self,
        message_id: str,
        response: str,
    ) -> bool:
        """Send a board response to a message."""
        msg_row = self._db.fetchone(
            "SELECT channel_id, thread_id FROM messages WHERE id = ?",
            (message_id,),
        )

        if not msg_row:
            return False

        channel_id = msg_row["channel_id"]
        thread_id = msg_row["thread_id"] or message_id

        ceo = self._get_ceo()
        if not ceo:
            logger.warning("Cannot send board response: CEO worker not found")
            return False

        response_id = f"msg-{str(uuid.uuid4())[:8]}"
        now = datetime.now()

        try:
            self._db.execute(
                """INSERT INTO messages
                   (id, channel_id, thread_id, parent_id, from_worker_id, content,
                    priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 3, 'immediate', ?)""",
                (response_id, channel_id, thread_id, message_id, ceo.id, response, now),
            )
            self._db.connection.commit()

            self._mark_message_read(message_id)

            return True
        except Exception as e:
            logger.error(f"Failed to send board response to message {message_id}: {e}")
            return False

    # ==================
    # CEO BRIEFING
    # ==================

    def send_ceo_briefing(self, briefing_content: str) -> bool:
        """Send briefing to CEO as high-priority message."""
        try:
            from cli.core.queries import create_message, generate_id
            from cli.core.notifications import create_notification_bead
        except ImportError:
            logger.warning(
                "CLI module not available; falling back to direct SQL for CEO briefing."
            )
            return self._send_ceo_briefing_fallback(briefing_content)

        try:
            ceo = self._get_ceo()
            if not ceo:
                return False

            channel_id = self._get_board_channel_id()
            if not channel_id:
                return False

            if "CEO Briefing" not in briefing_content:
                content = f"# CEO Briefing\n\n{briefing_content}"
            else:
                content = briefing_content

            message = create_message(
                db=self._db,
                channel_id=channel_id,
                from_worker_id=ceo.id,
                content=content,
                priority=0,
                time_sensitivity="immediate",
                message_id=generate_id("msg"),
            )

            create_notification_bead(
                db=self._db,
                worker_id=ceo.id,
                message_id=message.id,
                channel_id=channel_id,
                priority=0,
            )

            return True
        except Exception as e:
            logger.error(f"Failed to send CEO briefing: {e}")
            return False

    def _send_ceo_briefing_fallback(self, briefing_content: str) -> bool:
        """Fallback to direct SQL when CLI helpers are unavailable."""
        try:
            ceo = self._get_ceo()
            if not ceo:
                return False

            channel_id = self._get_board_channel_id()
            if not channel_id:
                return False

            if "CEO Briefing" not in briefing_content:
                content = f"# CEO Briefing\n\n{briefing_content}"
            else:
                content = briefing_content

            now = datetime.now()
            message_id = f"msg-{str(uuid.uuid4())[:8]}"
            self._db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, 0, 'immediate', ?)""",
                (message_id, channel_id, ceo.id, content, now),
            )

            notification_id = f"nb-{str(uuid.uuid4())[:8]}"
            self._db.execute(
                """INSERT INTO notification_beads
                   (id, worker_id, message_id, channel_id, status, priority, created_at, read_at, expires_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, NULL, NULL)""",
                (notification_id, ceo.id, message_id, channel_id, now),
            )
            self._db.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to send CEO briefing (fallback): {e}")
            return False

    def update_briefing(self, briefing_content: str) -> bool:
        """Update CEO briefing file and notify CEO."""
        try:
            config_path = self._org_path / "config" / "ceo_briefing.md"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(briefing_content)

            return self.send_ceo_briefing(briefing_content)
        except Exception as e:
            logger.error(f"Failed to update briefing: {e}")
            return False

    # ==================
    # SESSION CLEANUP
    # ==================

    def cleanup_stale_session(self, worker_id: str, tmux_session_name: Optional[str]) -> bool:
        """Cleanup a stale session for a worker."""
        try:
            self._db.execute(
                """UPDATE sessions
                   SET tmux_session_name = NULL,
                       state = 'stopped',
                       stopped_at = CURRENT_TIMESTAMP
                   WHERE worker_id = ?""",
                (worker_id,)
            )
            self._db.connection.commit()

            self._db.execute(
                """UPDATE worker_state
                   SET runtime_status = 'stopped',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE worker_id = ?""",
                (worker_id,)
            )
            self._db.connection.commit()

            try:
                from cli.core.sessions.binding_manager import get_binding_manager
                manager = get_binding_manager(self._db)
                manager.unbind(worker_id)
            except (ImportError, Exception) as e:
                logger.debug(f"Could not unbind session for {worker_id}: {e}")

            logger.info(f"Cleaned up stale session for worker {worker_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cleanup stale session for {worker_id}: {e}")
            return False

    # ==================
    # PROVIDER CONFIGURATION
    # ==================

    def set_default_provider(self, provider_name: str) -> tuple[bool, str]:
        """Set the default provider for the org by updating providers.yaml directly."""
        try:
            from cli.core.sessions.registry import get_default_registry

            config_path = self._org_path / "config" / "providers.yaml"
            if not config_path.exists():
                return False, f"Provider config not found: {config_path}"

            registry = get_default_registry()
            if not registry.has(provider_name):
                available = registry.list_adapters()
                return False, f"Unknown provider '{provider_name}'. Available: {', '.join(sorted(available))}"

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            config["default"] = provider_name

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)

            return True, f"Default provider set to {provider_name}"

        except Exception as e:
            return False, f"Error setting provider: {e}"

    def validate_provider_config(self) -> tuple[bool, list[str]]:
        """Validate provider configuration by reading providers.yaml directly."""
        try:
            from cli.core.sessions.registry import get_default_registry

            config_path = self._org_path / "config" / "providers.yaml"
            if not config_path.exists():
                return False, [f"Provider config not found: {config_path}"]

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            registry = get_default_registry()
            available = set(registry.list_all())
            errors = []

            default = config.get("default")
            if default and default not in available:
                errors.append(f"Default provider '{default}' is not registered")

            for name in config.get("authorized_providers", []):
                if name not in available:
                    errors.append(f"Authorized provider '{name}' is not registered")

            return (len(errors) == 0), errors

        except Exception as e:
            return False, [f"Error validating providers: {e}"]

    # ==================
    # CURSOR UPDATES
    # ==================

    def update_poll_cursor(self, client_id: str, last_change_id: int) -> None:
        """Update the poll cursor position for a client."""
        try:
            self._db.execute(
                """INSERT INTO status_change_cursors (client_id, last_change_id, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(client_id) DO UPDATE SET
                       last_change_id = excluded.last_change_id,
                       updated_at = excluded.updated_at""",
                (client_id, last_change_id)
            )
            self._db.connection.commit()
        except Exception as e:
            logger.debug(f"Error updating poll cursor: {e}")

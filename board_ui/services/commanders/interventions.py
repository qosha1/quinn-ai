"""Worker-level board interventions: pause / resume / fire."""

import uuid
from datetime import datetime
from typing import Optional

from cli.core.queries import update_worker_runtime_status
from cli.core.worker import Worker
from shared.enums import WorkerLifecycleStatus
from shared.exceptions import InvalidStateTransition, WorkerNotFound

from ...logging_config import get_board_logger
from ._context import OrgContext

logger = get_board_logger(__name__)


class InterventionsCommander:
    """Pause, resume, and fire workers; log + notify CEO of each action."""

    def __init__(self, ctx: OrgContext) -> None:
        self._ctx = ctx

    def pause_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Pause a worker by stopping its session."""
        try:
            worker = Worker.get(self._ctx.db, worker_id)
            worker.stop_session()

            self._log_intervention("pause", worker_id, reason or "Board paused worker")
            self._notify_ceo("pause", worker_id, reason or "Board paused worker")
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
            update_worker_runtime_status(self._ctx.db, worker_id, "starting")

            self._log_intervention("resume", worker_id, "Board resumed worker")
            self._notify_ceo("resume", worker_id, "Board resumed worker")
            return True
        except Exception as e:
            logger.error(f"Error resuming worker {worker_id}: {e}")
            return False

    def fire_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Terminate a worker via direct lifecycle transitions."""
        try:
            worker = Worker(self._ctx.db, worker_id, org_path=self._ctx.org_path)
            _ = worker.name  # raises WorkerNotFound if missing

            if worker.lifecycle_status == WorkerLifecycleStatus.ACTIVE.value:
                worker.start_offboarding()

            # Stop session in DB if still running (terminate() only handles in-memory sessions)
            if worker.runtime_status in ("starting", "running", "idle", "working", "blocked"):
                try:
                    worker.stop_session()
                except InvalidStateTransition:
                    pass  # already stopped or not stoppable

            worker.terminate()

            self._log_intervention("fire", worker_id, reason or "Board fired worker")
            self._notify_ceo("fire", worker_id, reason or "No reason provided")
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
        """Log intervention to board-channel as a priority-3 message."""
        try:
            channel_id = self._ctx.get_board_channel_id()
            if not channel_id:
                return

            ceo = self._ctx.get_ceo()
            if not ceo:
                logger.warning("Cannot log intervention: CEO worker not found")
                return

            now = datetime.now()
            message_id = f"msg-{str(uuid.uuid4())[:8]}"
            content = (
                f"**INTERVENTION: {action.upper()}**\n\n"
                f"Worker: {worker_id}\n"
                f"Reason: {reason}\n"
                f"Time: {now.isoformat()}"
            )

            self._ctx.db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, 3, 'immediate', ?)""",
                (message_id, channel_id, ceo.id, content, now),
            )
            self._ctx.db.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to log intervention: {e}")

    def _notify_ceo(self, action: str, worker_id: str, reason: str) -> None:
        """Notify CEO of intervention by creating a priority-4 notification bead."""
        try:
            channel_id = self._ctx.get_board_channel_id()
            if not channel_id:
                return

            ceo = self._ctx.get_ceo()
            if not ceo:
                logger.warning("Cannot notify CEO: CEO worker not found")
                return

            now = datetime.now()
            message_id = f"msg-{str(uuid.uuid4())[:8]}"
            content = (
                f"**BOARD INTERVENTION NOTIFICATION**\n\n"
                f"Action: {action.upper()}\n"
                f"Worker: {worker_id}\n"
                f"Reason: {reason}\n"
                f"Time: {now.isoformat()}"
            )

            self._ctx.db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, 4, 'immediate', ?)""",
                (message_id, channel_id, ceo.id, content, now),
            )

            notification_id = f"nb-{str(uuid.uuid4())[:8]}"
            self._ctx.db.execute(
                """INSERT INTO notification_beads
                   (id, worker_id, message_id, channel_id, status, priority, created_at, read_at, expires_at)
                   VALUES (?, ?, ?, ?, 'pending', 4, ?, NULL, NULL)""",
                (notification_id, ceo.id, message_id, channel_id, now),
            )

            self._ctx.db.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to notify CEO: {e}")

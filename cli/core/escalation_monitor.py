"""Escalation monitoring service.

Background service that monitors worker activity and creates escalations
when workers are idle for too long. This addresses GAP 4: ensuring workers
who are stuck get help automatically.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.db import Database, open_database, get_org_db_path
from core.worker import Worker
from core.bd_wrapper import run_bd
from core.constants import (
    DEFAULT_ESCALATION_POLL_INTERVAL,
    DEFAULT_ESCALATION_TIMEOUT_CEO,
    DEFAULT_ESCALATION_TIMEOUT_MANAGER,
    DEFAULT_ESCALATION_TIMEOUT_WORKER,
)
from shared.state_machines import ESCALATION_TRANSITIONS

_logger = logging.getLogger(__name__)


class EscalationMonitor:
    """Background monitor that detects idle workers and creates escalations.

    Runs in a separate thread, periodically checking worker activity and
    escalating to managers/board when workers are idle for too long.
    """

    def __init__(
        self,
        org_path: Path,
        poll_interval: float = DEFAULT_ESCALATION_POLL_INTERVAL,
        board_notifier=None,
    ):
        """Initialize escalation monitor.

        Args:
            org_path: Path to organization directory
            poll_interval: How often to check for idle workers (seconds)
            board_notifier: Optional BoardNotifier for board communication
        """
        self.org_path = org_path
        self.poll_interval = poll_interval
        self.board_notifier = board_notifier
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the escalation monitor in a background thread."""
        if self._running:
            _logger.warning("Escalation monitor already running")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="EscalationMonitor")
        self._thread.start()
        _logger.info("Escalation monitor started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the escalation monitor.

        Args:
            timeout: Maximum time to wait for monitor to stop (seconds)
        """
        if not self._running:
            return

        _logger.info("Stopping escalation monitor...")
        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                _logger.warning("Escalation monitor did not stop gracefully")

        _logger.info("Escalation monitor stopped")

    def is_running(self) -> bool:
        """Check if monitor is running.

        Returns:
            True if monitor is running
        """
        return self._running

    def _monitor_loop(self) -> None:
        """Main monitoring loop (runs in background thread)."""
        _logger.debug("Escalation monitor loop started")

        while self._running:
            try:
                self._check_workers()
            except Exception as e:
                _logger.error(f"Error in escalation monitor: {e}", exc_info=True)

            # Wait for next poll or stop signal
            self._stop_event.wait(timeout=self.poll_interval)

        _logger.debug("Escalation monitor loop exited")

    def _check_workers(self) -> None:
        """Check all active workers for idle state and escalate if needed."""
        db_path = get_org_db_path(self.org_path)
        if not db_path.exists():
            return

        db = open_database(db_path)
        try:
            # Get all active workers
            rows = db.fetchall(
                """SELECT id, role, manager_id, updated_at
                   FROM workers
                   WHERE status IN ('onboarding', 'active')"""
            )

            for row in rows:
                worker_id = row["id"]
                worker_role = row["role"]
                manager_id = row["manager_id"]
                last_updated = row["updated_at"]

                # Check escalation state
                self._check_worker_escalation(
                    db, worker_id, worker_role, manager_id, last_updated
                )

        finally:
            db.close()

    def _check_worker_escalation(
        self,
        db: Database,
        worker_id: str,
        worker_role: str,
        manager_id: Optional[str],
        last_updated: datetime,
    ) -> None:
        """Check if worker needs escalation.

        Args:
            db: Database instance
            worker_id: Worker ID
            worker_role: Worker role
            manager_id: Manager ID (None for CEO)
            last_updated: When worker was last updated
        """
        # Get or create escalation state
        state_row = db.fetchone(
            "SELECT * FROM worker_escalation_state WHERE worker_id = ?",
            (worker_id,)
        )

        now = datetime.now()

        if not state_row:
            # Initialize escalation state
            db.execute(
                """INSERT INTO worker_escalation_state
                   (worker_id, current_state, last_activity_at)
                   VALUES (?, 'normal', ?)""",
                (worker_id, now)
            )
            db.connection.commit()
            return

        current_state = state_row["current_state"]
        last_activity = state_row["last_activity_at"]
        idle_since = state_row["idle_since"]

        # Determine timeout based on role
        timeout_minutes = self._get_timeout_for_role(worker_role, manager_id)
        timeout_delta = timedelta(minutes=timeout_minutes)

        # Calculate idle duration
        if isinstance(last_activity, str):
            last_activity = datetime.fromisoformat(last_activity)

        idle_duration = now - last_activity

        # State machine logic
        if current_state == "normal":
            if idle_duration > timeout_delta:
                # Worker is idle, create escalation
                self._create_escalation(db, worker_id, manager_id, idle_duration)
                self._transition_state(db, worker_id, "escalated_pending", now)

        elif current_state == "idle_warning":
            if idle_duration > timeout_delta:
                # Warning period expired, escalate
                self._create_escalation(db, worker_id, manager_id, idle_duration)
                self._transition_state(db, worker_id, "escalated_pending", now)
            elif idle_duration < timedelta(minutes=5):
                # Activity resumed
                self._transition_state(db, worker_id, "normal", now)

        elif current_state == "escalated_pending":
            # Check if escalation was resolved (would be marked by external action)
            # For now, stay in this state until manually resolved
            pass

        elif current_state == "escalated_resolved":
            # Worker was escalated but now resolved, return to normal
            self._transition_state(db, worker_id, "normal", now)

    def _get_timeout_for_role(self, role: str, manager_id: Optional[str]) -> int:
        """Get escalation timeout for worker role.

        Args:
            role: Worker role
            manager_id: Manager ID (None for CEO)

        Returns:
            Timeout in minutes
        """
        is_ceo = manager_id is None and role.upper() == "CEO"
        is_manager = manager_id is None and not is_ceo

        if is_ceo:
            return DEFAULT_ESCALATION_TIMEOUT_CEO
        elif is_manager:
            return DEFAULT_ESCALATION_TIMEOUT_MANAGER
        else:
            return DEFAULT_ESCALATION_TIMEOUT_WORKER

    def _transition_state(
        self,
        db: Database,
        worker_id: str,
        new_state: str,
        now: datetime,
    ) -> None:
        """Transition worker to new escalation state.

        Args:
            db: Database instance
            worker_id: Worker ID
            new_state: New escalation state
            now: Current timestamp
        """
        # Validate transition
        current_row = db.fetchone(
            "SELECT current_state FROM worker_escalation_state WHERE worker_id = ?",
            (worker_id,)
        )

        if current_row:
            current_state = current_row["current_state"]
            allowed_transitions = ESCALATION_TRANSITIONS.get(current_state, [])

            if new_state not in allowed_transitions:
                _logger.warning(
                    f"Invalid escalation state transition for {worker_id}: "
                    f"{current_state} -> {new_state}"
                )
                return

        # Update state
        db.execute(
            """UPDATE worker_escalation_state
               SET current_state = ?,
                   updated_at = ?,
                   idle_since = CASE WHEN ? = 'escalated_pending' THEN ? ELSE NULL END
               WHERE worker_id = ?""",
            (new_state, now, new_state, now, worker_id)
        )
        db.connection.commit()

        _logger.info(f"Worker {worker_id} escalation state: {new_state}")

    def _create_escalation(
        self,
        db: Database,
        worker_id: str,
        manager_id: Optional[str],
        idle_duration: timedelta,
    ) -> None:
        """Create escalation bead for idle worker.

        Args:
            db: Database instance
            worker_id: Idle worker ID
            manager_id: Manager to escalate to (None for board)
            idle_duration: How long worker has been idle
        """
        # Determine escalation target
        if manager_id:
            escalation_target = manager_id
            target_name = "manager"
        else:
            escalation_target = "board"
            target_name = "Board"

        # Get worker info
        worker = Worker.get(db, worker_id)

        # Create escalation bead using bd CLI
        idle_minutes = int(idle_duration.total_seconds() / 60)
        title = f"Worker idle: {worker.name} ({idle_minutes}m)"
        description = (
            f"Worker {worker.name} (role: {worker.role}) has been idle for {idle_minutes} minutes "
            f"without making progress. They may be blocked or stuck.\n\n"
            f"**Suggested actions:**\n"
            f"- Check their session logs\n"
            f"- Review their current task\n"
            f"- Send them a message to check in\n"
            f"- Provide unblocking guidance if stuck"
        )

        try:
            # Create bead via bd CLI
            result = run_bd(
                self.org_path,
                [
                    "create",
                    f"--title={title}",
                    f"--description={description}",
                    "--type=ask",
                    "--priority=1",  # High priority
                    f"--assignee={escalation_target}",
                ],
                worker_id="system",
            )

            if result.returncode == 0:
                _logger.info(f"Created escalation for {worker_id} -> {target_name}")

                # Update escalation state with bead ID (would need to parse bd output)
                # For now, just mark that escalation was created
                db.execute(
                    """UPDATE worker_escalation_state
                       SET escalation_created_at = ?,
                           escalation_target_id = ?
                       WHERE worker_id = ?""",
                    (datetime.now(), manager_id, worker_id)
                )
                db.connection.commit()

                # Notify board if notifier available
                if self.board_notifier:
                    try:
                        self.board_notifier.notify_worker_idle(
                            worker_id=worker_id,
                            worker_name=worker.name,
                            idle_minutes=idle_minutes,
                            role=worker.role,
                        )
                    except Exception as e:
                        _logger.warning(f"Failed to send board notification: {e}")

            else:
                _logger.error(
                    f"Failed to create escalation bead: {result.stderr}"
                )

        except Exception as e:
            _logger.error(f"Error creating escalation bead: {e}", exc_info=True)

    def update_worker_activity(self, worker_id: str) -> None:
        """Update worker's last activity timestamp.

        Call this when worker shows activity (commits, updates beads, etc.)

        Args:
            worker_id: Worker ID
        """
        db_path = get_org_db_path(self.org_path)
        if not db_path.exists():
            return

        db = open_database(db_path)
        try:
            now = datetime.now()
            db.execute(
                """INSERT INTO worker_escalation_state
                   (worker_id, current_state, last_activity_at, updated_at)
                   VALUES (?, 'normal', ?, ?)
                   ON CONFLICT(worker_id) DO UPDATE SET
                       last_activity_at = ?,
                       updated_at = ?""",
                (worker_id, now, now, now, now)
            )
            db.connection.commit()
        finally:
            db.close()

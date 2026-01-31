"""Continuation engine for worker monitoring and graduated nudging.

Replaces EscalationMonitor with a more sophisticated system that:
1. Monitors workers for activity using ActivitySensor
2. Applies role-based continuation policies
3. Sends graduated prompts via SessionPrompter
4. Creates escalation beads at final timeout

This is Phase 3 of the continuation system - the monitoring engine.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread, Event
from typing import Optional

from .db import Database, open_database, get_org_db_path
from .activity_sensor import ActivitySensor
from .session_prompter import SessionPrompter
from .queries.worker import get_worker, is_worker_manager
from .bd_wrapper import run_bd
from .constants import (
    CONTINUATION_NUDGE_1_MINUTES,
    CONTINUATION_NUDGE_2_MINUTES,
    CONTINUATION_WARNING_MINUTES,
    CONTINUATION_ESCALATE_MINUTES,
    CONTINUATION_NUDGE_1_MINUTES_CEO,
    CONTINUATION_NUDGE_2_MINUTES_CEO,
    CONTINUATION_WARNING_MINUTES_CEO,
    CONTINUATION_ESCALATE_MINUTES_CEO,
    CONTINUATION_NUDGE_1_MINUTES_MANAGER,
    CONTINUATION_NUDGE_2_MINUTES_MANAGER,
    CONTINUATION_WARNING_MINUTES_MANAGER,
    CONTINUATION_ESCALATE_MINUTES_MANAGER,
    CONTINUATION_ENGINE_POLL_INTERVAL,
)

logger = logging.getLogger(__name__)


@dataclass
class ContinuationPolicy:
    """Policy for worker continuation nudges.

    Defines the timing thresholds for graduated prompts based on worker role.
    """

    nudge_1_minutes: int
    nudge_2_minutes: int
    warning_minutes: int
    escalate_minutes: int

    @classmethod
    def for_worker(
        cls,
        is_ceo: bool,
        is_manager: bool,
    ) -> "ContinuationPolicy":
        """Get policy for worker role.

        Args:
            is_ceo: True if worker is CEO (no manager)
            is_manager: True if worker has direct reports

        Returns:
            ContinuationPolicy with role-appropriate timings
        """
        if is_ceo:
            return cls(
                nudge_1_minutes=CONTINUATION_NUDGE_1_MINUTES_CEO,
                nudge_2_minutes=CONTINUATION_NUDGE_2_MINUTES_CEO,
                warning_minutes=CONTINUATION_WARNING_MINUTES_CEO,
                escalate_minutes=CONTINUATION_ESCALATE_MINUTES_CEO,
            )
        elif is_manager:
            return cls(
                nudge_1_minutes=CONTINUATION_NUDGE_1_MINUTES_MANAGER,
                nudge_2_minutes=CONTINUATION_NUDGE_2_MINUTES_MANAGER,
                warning_minutes=CONTINUATION_WARNING_MINUTES_MANAGER,
                escalate_minutes=CONTINUATION_ESCALATE_MINUTES_MANAGER,
            )
        else:
            return cls(
                nudge_1_minutes=CONTINUATION_NUDGE_1_MINUTES,
                nudge_2_minutes=CONTINUATION_NUDGE_2_MINUTES,
                warning_minutes=CONTINUATION_WARNING_MINUTES,
                escalate_minutes=CONTINUATION_ESCALATE_MINUTES,
            )


class ContinuationEngine:
    """Monitors workers and sends continuation prompts.

    Background service that:
    1. Polls active workers every 60 seconds
    2. Checks last activity using ActivitySensor
    3. Applies role-based ContinuationPolicy
    4. Sends graduated prompts via SessionPrompter
    5. Creates escalation beads at final timeout
    """

    def __init__(
        self,
        org_path: Path,
        poll_interval: float = CONTINUATION_ENGINE_POLL_INTERVAL,
    ):
        """Initialize continuation engine.

        Args:
            org_path: Path to organization directory
            poll_interval: How often to check workers (seconds)
        """
        self.org_path = org_path
        self.poll_interval = poll_interval
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._running = False

        # Track when we last sent each prompt type per worker
        # Format: {worker_id: {"soft_check": datetime, "status_request": datetime, ...}}
        self._last_prompts: dict[str, dict[str, datetime]] = {}

    def start(self) -> None:
        """Start monitoring in background thread."""
        if self._running:
            logger.warning("Continuation engine already running")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            daemon=True,
            name="ContinuationEngine",
        )
        self._thread.start()
        logger.info("Continuation engine started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop monitoring gracefully.

        Args:
            timeout: Maximum time to wait for thread to stop (seconds)
        """
        if not self._running:
            return

        logger.info("Stopping continuation engine...")
        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("Continuation engine did not stop gracefully")

        logger.info("Continuation engine stopped")

    def is_running(self) -> bool:
        """Check if engine is running.

        Returns:
            True if monitoring is active
        """
        return self._running

    def _run(self) -> None:
        """Main monitoring loop (runs in background thread)."""
        logger.debug("Continuation engine loop started")

        while self._running:
            try:
                self._check_all_workers()
            except Exception as e:
                logger.error(f"Error in continuation engine: {e}", exc_info=True)

            # Wait for next poll or stop signal
            self._stop_event.wait(timeout=self.poll_interval)

        logger.debug("Continuation engine loop exited")

    def _check_all_workers(self) -> None:
        """Check all active workers for activity and apply policies."""
        db_path = get_org_db_path(self.org_path)
        if not db_path.exists():
            return

        db = open_database(db_path)
        try:
            # Get all active workers
            workers = db.fetchall(
                "SELECT id, manager_id FROM workers WHERE status = 'active'"
            )

            sensor = ActivitySensor(db, self.org_path)
            prompter = SessionPrompter(db, self.org_path)

            for worker_row in workers:
                worker_id = worker_row["id"]
                manager_id = worker_row["manager_id"]

                # Determine if CEO/manager
                is_ceo = manager_id is None
                is_manager = is_worker_manager(db, worker_id)

                policy = ContinuationPolicy.for_worker(is_ceo, is_manager)

                self._check_worker(
                    db, sensor, prompter,
                    worker_id, manager_id, policy
                )

        finally:
            db.close()

    def _check_worker(
        self,
        db: Database,
        sensor: ActivitySensor,
        prompter: SessionPrompter,
        worker_id: str,
        manager_id: Optional[str],
        policy: ContinuationPolicy,
    ) -> None:
        """Check single worker and apply continuation policy.

        Args:
            db: Database instance
            sensor: ActivitySensor for checking last activity
            prompter: SessionPrompter for sending prompts
            worker_id: Worker ID to check
            manager_id: Worker's manager ID (None for CEO)
            policy: ContinuationPolicy for this worker's role
        """
        last_activity = sensor.get_last_activity(worker_id, min_strength=3)
        if not last_activity:
            # No activity yet, skip
            return

        now = datetime.now()
        idle_minutes = (now - last_activity).total_seconds() / 60

        # Check if we need to escalate
        if idle_minutes >= policy.escalate_minutes:
            # Check if we already escalated recently (avoid spam)
            if not self._should_send_prompt(worker_id, "escalation", minutes_between=60):
                return

            self._escalate(db, worker_id, manager_id, idle_minutes)
            self._mark_prompt_sent(worker_id, "escalation")

        # Send final warning
        elif idle_minutes >= policy.warning_minutes:
            if not self._should_send_prompt(worker_id, "final_warning", minutes_between=10):
                return

            prompter.send_final_warning(worker_id)
            self._mark_prompt_sent(worker_id, "final_warning")

        # Send status request
        elif idle_minutes >= policy.nudge_2_minutes:
            if not self._should_send_prompt(worker_id, "status_request", minutes_between=15):
                return

            prompter.send_status_request(worker_id)
            self._mark_prompt_sent(worker_id, "status_request")

        # Send soft check
        elif idle_minutes >= policy.nudge_1_minutes:
            if not self._should_send_prompt(worker_id, "soft_check", minutes_between=10):
                return

            prompter.send_soft_check(worker_id)
            self._mark_prompt_sent(worker_id, "soft_check")

    def _should_send_prompt(
        self,
        worker_id: str,
        prompt_type: str,
        minutes_between: int,
    ) -> bool:
        """Check if enough time has passed since last prompt of this type.

        Prevents spamming workers with duplicate prompts.

        Args:
            worker_id: Worker ID
            prompt_type: Type of prompt
            minutes_between: Minimum minutes between prompts of this type

        Returns:
            True if we should send the prompt
        """
        if worker_id not in self._last_prompts:
            return True

        last_sent = self._last_prompts[worker_id].get(prompt_type)
        if not last_sent:
            return True

        minutes_since = (datetime.now() - last_sent).total_seconds() / 60
        return minutes_since >= minutes_between

    def _mark_prompt_sent(
        self,
        worker_id: str,
        prompt_type: str,
    ) -> None:
        """Mark that we sent a prompt to avoid duplicates.

        Args:
            worker_id: Worker ID
            prompt_type: Type of prompt sent
        """
        if worker_id not in self._last_prompts:
            self._last_prompts[worker_id] = {}

        self._last_prompts[worker_id][prompt_type] = datetime.now()

    def _escalate(
        self,
        db: Database,
        worker_id: str,
        manager_id: Optional[str],
        idle_minutes: float,
    ) -> None:
        """Create escalation bead for idle worker.

        Args:
            db: Database instance
            worker_id: Idle worker ID
            manager_id: Manager to escalate to (None for board)
            idle_minutes: How long worker has been idle
        """
        # Determine escalation target
        if manager_id:
            escalation_target = manager_id
            target_name = "manager"
        else:
            escalation_target = "board"
            target_name = "Board"

        # Get worker info
        worker = get_worker(db, worker_id)
        if not worker:
            logger.error(f"Worker {worker_id} not found, cannot escalate")
            return

        # Create escalation bead using bd CLI
        idle_mins = int(idle_minutes)
        title = f"Worker idle: {worker.name} ({idle_mins}m)"
        description = (
            f"Worker {worker.name} (role: {worker.role}) has been idle for {idle_mins} minutes "
            f"without making progress. They may be blocked or stuck.\n\n"
            f"**Suggested actions:**\n"
            f"- Check their session logs: `qn wrkr logs {worker_id}`\n"
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
                logger.info(f"Created escalation for {worker_id} -> {target_name}")
            else:
                logger.error(f"Failed to create escalation bead: {result.stderr}")

        except Exception as e:
            logger.error(f"Error creating escalation bead: {e}", exc_info=True)


__all__ = [
    "ContinuationPolicy",
    "ContinuationEngine",
]

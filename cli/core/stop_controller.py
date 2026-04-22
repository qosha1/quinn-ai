"""
Org Stop Controller - graceful shutdown orchestration.

Implements the complete org stop sequence:
1. Validation and preparation
2. Send wrap-up requests to all workers
3. Wait for acknowledgements (with per-role timeouts)
4. Stop sessions (graceful then force)
5. Update worker states
6. Persist state and cleanup
7. Transition org to STOPPED

The controller coordinates between workers, sessions, and the org to ensure
a clean shutdown with state preservation for resume.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .constants import (
    STOP_TIMEOUT_BY_ROLE,
    DEFAULT_STOP_TIMEOUT,
    STOP_ACK_POLL_INTERVAL,
    STOP_ACK_TIMEOUT_RATIO,
    STOP_SESSION_GRACE_PERIOD,
    STOP_SESSION_FORCE_TIMEOUT,
    WRAPUP_MESSAGE_TYPE,
    WRAPUP_ACK_MESSAGE_TYPE,
    RESUME_STATE_TTL_HOURS,
)
from .db import Database
from .org import Org
from .worker import Worker
from .sessions import (
    get_active_sessions,
    stop_all_sessions,
    StopAllSessionsResult,
)
from .sessions.tmux_spawner import TmuxSpawner

if TYPE_CHECKING:
    from .queries.worker import Worker as WorkerData

_logger = logging.getLogger(__name__)


@dataclass
class WorkerStopState:
    """Tracks stop state for a single worker."""

    worker_id: str
    worker_name: str
    role: str
    timeout_seconds: int
    wrapup_sent_at: Optional[datetime] = None
    ack_received_at: Optional[datetime] = None
    ack_message: Optional[str] = None
    session_stopped: bool = False
    state_saved: bool = False
    error: Optional[str] = None


@dataclass
class StopPhaseResult:
    """Result of a stop phase."""

    phase: int
    name: str
    success: bool
    duration_seconds: float
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class OrgStopResult:
    """Complete result of org stop operation."""

    success: bool
    phases: list[StopPhaseResult] = field(default_factory=list)
    workers_stopped: int = 0
    workers_acked: int = 0
    sessions_terminated: int = 0
    states_saved: int = 0
    errors: list[str] = field(default_factory=list)
    total_duration_seconds: float = 0.0


class OrgStopController:
    """Orchestrates the org stop sequence.

    Usage:
        controller = OrgStopController(db, org_path, org)
        result = controller.execute(force=False, save_state=True)
    """

    def __init__(
        self,
        db: Database,
        org_path: Path,
        org: Org,
        tmux_spawner: Optional[TmuxSpawner] = None,
    ):
        """Initialize stop controller.

        Args:
            db: Database instance
            org_path: Path to org directory
            org: Org instance
            tmux_spawner: Optional TmuxSpawner (for testing)
        """
        self.db = db
        self.org_path = org_path
        self.org = org
        self.tmux_spawner = tmux_spawner or TmuxSpawner()
        self._worker_states: dict[str, WorkerStopState] = {}
        self._result = OrgStopResult(success=False)
        self._start_time: Optional[datetime] = None

    def execute(
        self,
        force: bool = False,
        save_state: bool = True,
        cleanup: bool = True,
        graceful_timeout: Optional[int] = None,
    ) -> OrgStopResult:
        """Execute the complete stop sequence.

        Args:
            force: Skip graceful shutdown, force kill immediately
            save_state: Save worker state for resume
            cleanup: Run cleanup after stop
            graceful_timeout: Override default timeout (uses role-based if None)

        Returns:
            OrgStopResult with details of each phase
        """
        self._start_time = datetime.now()
        self._result = OrgStopResult(success=False)

        try:
            # Validation and preparation
            phase1 = self._validate_and_prepare()
            self._result.phases.append(phase1)
            if not phase1.success:
                return self._finalize_result()

            # If force mode, skip wrap-up and ack phases
            if not force:
                # Send wrap-up requests
                phase2 = self._send_wrapup_requests(graceful_timeout)
                self._result.phases.append(phase2)
                if not phase2.success:
                    _logger.warning("Send wrap-up requests had issues, continuing to wait for acknowledgements")

                # Wait for acknowledgements
                phase3 = self._wait_for_acknowledgements()
                self._result.phases.append(phase3)
                self._result.workers_acked = phase3.details.get("acks_received", 0)

            # Stop sessions
            phase4 = self._stop_sessions(force)
            self._result.phases.append(phase4)
            self._result.sessions_terminated = phase4.details.get("sessions_stopped", 0)

            # Update worker states
            phase5 = self._update_worker_states()
            self._result.phases.append(phase5)
            self._result.workers_stopped = phase5.details.get("workers_updated", 0)

            # Persist state and cleanup
            if save_state:
                phase6 = self._persist_state(cleanup)
                self._result.phases.append(phase6)
                self._result.states_saved = phase6.details.get("states_saved", 0)

            # Transition org to STOPPED
            phase7 = self._transition_org_to_stopped()
            self._result.phases.append(phase7)

            self._result.success = phase7.success

        except Exception as e:
            _logger.exception("Stop sequence failed unexpectedly")
            self._result.errors.append(f"Unexpected error: {e}")
            self._result.success = False

        return self._finalize_result()

    def _finalize_result(self) -> OrgStopResult:
        """Finalize and return the result."""
        if self._start_time:
            elapsed = datetime.now() - self._start_time
            self._result.total_duration_seconds = elapsed.total_seconds()
        return self._result

    # ===================
    # Validation and Preparation
    # ===================

    def _validate_and_prepare(self) -> StopPhaseResult:
        """Validate org can be stopped and prepare worker states."""
        start = time.time()

        try:
            # Validate org status
            from shared.enums import OrgStatus
            if self.org.status not in [OrgStatus.RUNNING.value, OrgStatus.STOPPED.value]:
                return StopPhaseResult(
                    phase=1,
                    name="Validation and Preparation",
                    success=False,
                    duration_seconds=time.time() - start,
                    message=f"Cannot stop org in '{self.org.status}' state",
                )

            # If already stopped, short-circuit
            if self.org.status == OrgStatus.STOPPED.value:
                return StopPhaseResult(
                    phase=1,
                    name="Validation and Preparation",
                    success=True,
                    duration_seconds=time.time() - start,
                    message="Org already stopped",
                    details={"already_stopped": True},
                )

            # Get active sessions and build worker states
            active_sessions = get_active_sessions(self.db)
            for session in active_sessions:
                worker_id = session.get("worker_id")
                if not worker_id:
                    continue

                try:
                    worker = Worker.get(self.db, worker_id)
                    timeout = self._get_worker_timeout(worker.role)
                    self._worker_states[worker_id] = WorkerStopState(
                        worker_id=worker_id,
                        worker_name=worker.name,
                        role=worker.role,
                        timeout_seconds=timeout,
                    )
                except Exception as e:
                    _logger.warning(f"Failed to load worker {worker_id}: {e}")

            return StopPhaseResult(
                phase=1,
                name="Validation and Preparation",
                success=True,
                duration_seconds=time.time() - start,
                message=f"Prepared {len(self._worker_states)} workers for stop",
                details={
                    "workers_prepared": len(self._worker_states),
                    "worker_ids": list(self._worker_states.keys()),
                },
            )

        except Exception as e:
            _logger.exception("Validation and preparation failed")
            return StopPhaseResult(
                phase=1,
                name="Validation and Preparation",
                success=False,
                duration_seconds=time.time() - start,
                message=f"Validation failed: {e}",
            )

    def _get_worker_timeout(self, role: str) -> int:
        """Get timeout for a worker role."""
        role_lower = role.lower()
        return STOP_TIMEOUT_BY_ROLE.get(role_lower, DEFAULT_STOP_TIMEOUT)

    # ===================
    # Send Wrap-up Requests
    # ===================

    def _send_wrapup_requests(
        self,
        graceful_timeout: Optional[int] = None,
    ) -> StopPhaseResult:
        """Send wrap-up notifications to all active workers."""
        start = time.time()

        if not self._worker_states:
            return StopPhaseResult(
                phase=2,
                name="Send Wrap-up Requests",
                success=True,
                duration_seconds=time.time() - start,
                message="No active workers to notify",
            )

        try:
            from .queries import (
                get_channel_by_name,
                create_default_org_channels,
                create_message,
            )
            from .notifications import create_notification_bead

            # Ensure general channel exists
            general = get_channel_by_name(self.db, "general")
            if general is None:
                create_default_org_channels(self.db)
                general = get_channel_by_name(self.db, "general")

            if not general:
                return StopPhaseResult(
                    phase=2,
                    name="Send Wrap-up Requests",
                    success=False,
                    duration_seconds=time.time() - start,
                    message="No general channel available",
                )

            # Get sender (CEO or system)
            sender_id = self.org.ceo_worker_id
            if not sender_id:
                # Use first worker as fallback
                sender_id = next(iter(self._worker_states.keys()), None)

            sent_count = 0
            errors = []
            now = datetime.now()

            for worker_id, state in self._worker_states.items():
                try:
                    timeout = graceful_timeout or state.timeout_seconds

                    # Create wrap-up message
                    message = create_message(
                        self.db,
                        channel_id=general.id,
                        from_worker_id=sender_id,
                        content=self._build_wrapup_message(state, timeout),
                        priority=0,  # Highest priority
                        time_sensitivity="immediate",
                    )

                    # Create notification bead for the worker
                    create_notification_bead(
                        self.db,
                        worker_id=worker_id,
                        message_id=message.id,
                        channel_id=general.id,
                        priority=0,
                    )

                    state.wrapup_sent_at = now
                    sent_count += 1
                    _logger.debug(f"Sent wrap-up to {state.worker_name}")

                except Exception as e:
                    error_msg = f"Failed to notify {worker_id}: {e}"
                    errors.append(error_msg)
                    state.error = str(e)
                    _logger.warning(error_msg)

            if errors:
                self._result.errors.extend(errors)

            return StopPhaseResult(
                phase=2,
                name="Send Wrap-up Requests",
                success=sent_count > 0 or not self._worker_states,
                duration_seconds=time.time() - start,
                message=f"Sent {sent_count}/{len(self._worker_states)} wrap-up notifications",
                details={
                    "sent_count": sent_count,
                    "error_count": len(errors),
                },
            )

        except Exception as e:
            _logger.exception("Send wrap-up requests failed")
            return StopPhaseResult(
                phase=2,
                name="Send Wrap-up Requests",
                success=False,
                duration_seconds=time.time() - start,
                message=f"Failed to send wrap-up requests: {e}",
            )

    def _build_wrapup_message(self, state: WorkerStopState, timeout: int) -> str:
        """Build wrap-up notification content."""
        return (
            f"**Workday Ending**\n\n"
            f"Worker: {state.worker_name} ({state.role})\n\n"
            f"Please wrap up your current work:\n"
            f"1. Save any work in progress to shared/\n"
            f"2. Document incomplete work in beads\n"
            f"3. Commit any changes\n\n"
            f"Timeout: {timeout} seconds\n\n"
            f"Reply with 'ACK' to acknowledge.\n"
            f"After timeout, your session will be terminated."
        )

    # ===================
    # Wait for Acknowledgements
    # ===================

    def _wait_for_acknowledgements(self) -> StopPhaseResult:
        """Wait for workers to acknowledge wrap-up."""
        start = time.time()

        if not self._worker_states:
            return StopPhaseResult(
                phase=3,
                name="Wait for Acknowledgements",
                success=True,
                duration_seconds=time.time() - start,
                message="No workers to wait for",
            )

        # Calculate deadline based on max timeout
        max_timeout = max(
            s.timeout_seconds for s in self._worker_states.values()
        )
        ack_timeout = int(max_timeout * STOP_ACK_TIMEOUT_RATIO)
        deadline = datetime.now() + timedelta(seconds=ack_timeout)

        acks_received = 0
        acks_expected = len(self._worker_states)

        _logger.info(f"Waiting up to {ack_timeout}s for {acks_expected} acknowledgements")

        # Poll for acknowledgements
        while datetime.now() < deadline:
            # Check for new acks
            new_acks = self._poll_for_acks()
            acks_received += new_acks

            if acks_received >= acks_expected:
                break

            time.sleep(STOP_ACK_POLL_INTERVAL)

        # Log unacked workers
        unacked = [
            s.worker_name for s in self._worker_states.values()
            if s.ack_received_at is None
        ]
        if unacked:
            _logger.warning(f"Workers did not ack: {', '.join(unacked)}")

        return StopPhaseResult(
            phase=3,
            name="Wait for Acknowledgements",
            success=True,  # Phase succeeds even if not all ack
            duration_seconds=time.time() - start,
            message=f"Received {acks_received}/{acks_expected} acknowledgements",
            details={
                "acks_received": acks_received,
                "acks_expected": acks_expected,
                "unacked_workers": unacked,
            },
        )

    def _poll_for_acks(self) -> int:
        """Poll for new acknowledgements. Returns count of new acks."""
        # For now, we check the notification_beads table for actioned status
        # A more sophisticated implementation would use a dedicated ack message type
        new_acks = 0

        for worker_id, state in self._worker_states.items():
            if state.ack_received_at is not None:
                continue  # Already acked

            # Check if worker has actioned the notification
            row = self.db.fetchone(
                """SELECT status, actioned_at FROM notification_beads
                   WHERE worker_id = ? AND status = 'actioned'
                   ORDER BY created_at DESC LIMIT 1""",
                (worker_id,)
            )

            if row and row["status"] == "actioned":
                state.ack_received_at = datetime.now()
                new_acks += 1
                _logger.debug(f"Received ack from {state.worker_name}")

        return new_acks

    # ===================
    # Stop Sessions
    # ===================

    def _stop_sessions(self, force: bool) -> StopPhaseResult:
        """Stop all worker sessions."""
        start = time.time()

        try:
            # First try graceful stop
            result: StopAllSessionsResult = stop_all_sessions(
                self.db,
                tmux_spawner=self.tmux_spawner,
                force=force,
            )

            # If graceful didn't get all and we're not forcing, wait and retry
            if not force and result.sessions_found > result.sessions_stopped:
                _logger.info(f"Waiting {STOP_SESSION_GRACE_PERIOD}s for graceful shutdown")
                time.sleep(STOP_SESSION_GRACE_PERIOD)

                # Force remaining
                remaining = get_active_sessions(self.db)
                if remaining:
                    _logger.info(f"Force stopping {len(remaining)} remaining sessions")
                    force_result = stop_all_sessions(
                        self.db,
                        tmux_spawner=self.tmux_spawner,
                        force=True,
                    )
                    result.sessions_stopped += force_result.sessions_stopped
                    result.tmux_sessions_killed += force_result.tmux_sessions_killed
                    result.errors.extend(force_result.errors)

            # Update worker states
            for state in self._worker_states.values():
                state.session_stopped = True

            if result.errors:
                self._result.errors.extend(result.errors)

            return StopPhaseResult(
                phase=4,
                name="Stop Sessions",
                success=result.sessions_stopped >= 0,  # Always "succeed" even if no sessions
                duration_seconds=time.time() - start,
                message=f"Stopped {result.sessions_stopped}/{result.sessions_found} sessions",
                details={
                    "sessions_found": result.sessions_found,
                    "sessions_stopped": result.sessions_stopped,
                    "tmux_killed": result.tmux_sessions_killed,
                    "errors": result.errors,
                },
            )

        except Exception as e:
            _logger.exception("Stop sessions failed")
            return StopPhaseResult(
                phase=4,
                name="Stop Sessions",
                success=False,
                duration_seconds=time.time() - start,
                message=f"Failed to stop sessions: {e}",
            )

    # ===================
    # Update Worker States
    # ===================

    def _update_worker_states(self) -> StopPhaseResult:
        """Update worker runtime states to stopped."""
        start = time.time()

        updated_count = 0
        errors = []

        for worker_id, state in self._worker_states.items():
            try:
                from .queries import update_worker_runtime_status
                update_worker_runtime_status(self.db, worker_id, "stopped")
                updated_count += 1
            except Exception as e:
                error_msg = f"Failed to update {worker_id}: {e}"
                errors.append(error_msg)
                state.error = str(e)

        if errors:
            self._result.errors.extend(errors)

        return StopPhaseResult(
            phase=5,
            name="Update Worker States",
            success=True,
            duration_seconds=time.time() - start,
            message=f"Updated {updated_count}/{len(self._worker_states)} workers",
            details={
                "workers_updated": updated_count,
                "errors": errors,
            },
        )

    # ===================
    # Persist State and Cleanup
    # ===================

    def _persist_state(self, cleanup: bool) -> StopPhaseResult:
        """Save worker resume states and run cleanup."""
        start = time.time()

        saved_count = 0
        errors = []

        for worker_id, state in self._worker_states.items():
            try:
                self._save_worker_resume_state(worker_id, state)
                state.state_saved = True
                saved_count += 1
            except Exception as e:
                error_msg = f"Failed to save state for {worker_id}: {e}"
                errors.append(error_msg)
                _logger.warning(error_msg)

        # Run cleanup if requested
        cleanup_result = {}
        if cleanup:
            try:
                from .notifications import run_notification_cleanup
                from .constants import DEFAULT_NOTIFICATION_RETENTION_DAYS
                cleanup_result = run_notification_cleanup(
                    self.db, DEFAULT_NOTIFICATION_RETENTION_DAYS
                )
            except Exception as e:
                errors.append(f"Cleanup failed: {e}")

        if errors:
            self._result.errors.extend(errors)

        return StopPhaseResult(
            phase=6,
            name="Persist State and Cleanup",
            success=True,
            duration_seconds=time.time() - start,
            message=f"Saved {saved_count} worker states",
            details={
                "states_saved": saved_count,
                "cleanup_result": cleanup_result,
                "errors": errors,
            },
        )

    def _save_worker_resume_state(
        self,
        worker_id: str,
        state: WorkerStopState,
    ) -> None:
        """Save worker resume state to database."""
        from .queries import get_worker_state
        from .queries.common import generate_id

        worker_state = get_worker_state(self.db, worker_id)

        # Get session info if available
        session_row = self.db.fetchone(
            "SELECT provider, model, working_directory FROM sessions WHERE worker_id = ?",
            (worker_id,)
        )

        # Calculate expiry
        expires_at = datetime.now() + timedelta(hours=RESUME_STATE_TTL_HOURS)

        # Build context JSON
        context = {
            "role": state.role,
            "worker_name": state.worker_name,
            "ack_received": state.ack_received_at is not None,
            "ack_message": state.ack_message,
        }

        # Insert resume state (upsert)
        self.db.execute(
            """INSERT OR REPLACE INTO worker_resume_states
               (id, worker_id, current_task_id, current_task_context,
                last_activity_at, tasks_completed, tasks_failed,
                session_provider, session_model, working_directory,
                wrapup_requested_at, wrapup_acked_at, ack_message,
                created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                generate_id("resume"),
                worker_id,
                worker_state.current_task_id if worker_state else None,
                json.dumps(context),
                worker_state.last_activity if worker_state else None,
                worker_state.tasks_completed if worker_state else 0,
                worker_state.tasks_failed if worker_state else 0,
                session_row["provider"] if session_row else None,
                session_row["model"] if session_row else None,
                session_row["working_directory"] if session_row else None,
                state.wrapup_sent_at,
                state.ack_received_at,
                state.ack_message,
                datetime.now(),
                expires_at,
            )
        )
        self.db.connection.commit()

    # ===================
    # Transition Org to STOPPED
    # ===================

    def _transition_org_to_stopped(self) -> StopPhaseResult:
        """Transition org to STOPPED state."""
        start = time.time()

        try:
            # Check if already stopped (from phase 1)
            from shared.enums import OrgStatus
            if self.org.status == OrgStatus.STOPPED.value:
                return StopPhaseResult(
                    phase=7,
                    name="Transition Org to STOPPED",
                    success=True,
                    duration_seconds=time.time() - start,
                    message="Org already stopped",
                )

            self.org.stop()

            return StopPhaseResult(
                phase=7,
                name="Transition Org to STOPPED",
                success=True,
                duration_seconds=time.time() - start,
                message=f"Org transitioned to {OrgStatus.STOPPED.value}",
            )

        except Exception as e:
            _logger.exception("Transition org to STOPPED failed")
            return StopPhaseResult(
                phase=7,
                name="Transition Org to STOPPED",
                success=False,
                duration_seconds=time.time() - start,
                message=f"Failed to transition org: {e}",
            )


# ===================
# HELPER FUNCTIONS
# ===================

def get_resume_state(db: Database, worker_id: str) -> Optional[dict]:
    """Get resume state for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Resume state dict or None if not found/expired
    """
    row = db.fetchone(
        """SELECT * FROM worker_resume_states
           WHERE worker_id = ? AND consumed_at IS NULL AND expires_at > ?""",
        (worker_id, datetime.now())
    )
    return dict(row) if row else None


def consume_resume_state(db: Database, worker_id: str) -> bool:
    """Mark resume state as consumed.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        True if state was consumed, False if not found
    """
    result = db.execute(
        """UPDATE worker_resume_states
           SET consumed_at = ? WHERE worker_id = ? AND consumed_at IS NULL""",
        (datetime.now(), worker_id)
    )
    db.connection.commit()
    return result.rowcount > 0


def cleanup_expired_resume_states(db: Database) -> int:
    """Clean up expired resume states.

    Args:
        db: Database instance

    Returns:
        Number of states deleted
    """
    result = db.execute(
        "DELETE FROM worker_resume_states WHERE expires_at < ?",
        (datetime.now(),)
    )
    db.connection.commit()
    return result.rowcount

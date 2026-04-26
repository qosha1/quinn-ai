"""
Worker lifecycle state management.

Handles lifecycle state transitions: pending → onboarding → active → offboarding → terminated.
Also handles suspend/unsuspend operations.
"""

import sqlite3
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from ..constants import BEAD_TYPE_ASK
from ..queries import (
    update_worker_status,
    get_worker,
    get_worker_team_memberships,
    remove_team_member,
    unsubscribe_from_all_channels,
)
from ..storage import WorkerStorageNotFound, StorageAlreadyFrozen
from ..logging import get_logger, log_worker_lifecycle
from shared import LIFECYCLE_TRANSITIONS, InvalidStateTransition
from shared.bd.client import BdCommandError

if TYPE_CHECKING:
    from ..db import Database
    from ..adapters.beads import BeadsClient


_logger = get_logger(__name__)


class WorkerLifecycleManager:
    """Manages lifecycle transitions for a worker.

    Handles:
    - Lifecycle state transitions
    - Onboarding workflow
    - Offboarding workflow
    - Suspension/unsuspension
    - Termination and cleanup
    """

    def __init__(self, worker: "WorkerBase"):
        """Initialize lifecycle manager.

        Args:
            worker: Parent Worker instance
        """
        self.worker = worker

    def _validate_lifecycle_transition(self, new_status: str) -> None:
        """Validate lifecycle state transition.

        Args:
            new_status: Attempted new status

        Raises:
            InvalidStateTransition: If transition is not allowed
        """
        current = self.worker.lifecycle_status
        valid = LIFECYCLE_TRANSITIONS.get(current, [])
        if new_status not in valid:
            raise InvalidStateTransition(current, new_status, valid)

    def start_onboarding(self) -> None:
        """Transition from pending to onboarding.

        Generates onboarding materials (BRIEFING.md, STORAGE.md, WELCOME.md)
        in the worker's storage directory.
        """
        old_status = self.worker.lifecycle_status
        self._validate_lifecycle_transition("onboarding")

        # Generate onboarding files before transitioning state
        from cli.core.onboarding import prepare_worker_onboarding
        org_path = self.worker._storage_mgr.get_org_path()
        prepare_worker_onboarding(self.worker.db, self.worker.id, org_path)

        update_worker_status(self.worker.db, self.worker.id, "onboarding")
        self.worker._worker_data = None  # Invalidate cache
        log_worker_lifecycle(_logger, self.worker.id, self.worker.name, old_status, "onboarding")

    def complete_onboarding(self) -> None:
        """Transition from onboarding to active.

        Sends a welcome message to #general channel announcing the new worker.
        """
        old_status = self.worker.lifecycle_status
        self._validate_lifecycle_transition("active")
        update_worker_status(self.worker.db, self.worker.id, "active")
        self.worker._worker_data = None
        log_worker_lifecycle(_logger, self.worker.id, self.worker.name, old_status, "active")

        # Send welcome message to general channel
        self._send_welcome_message()

    def _send_welcome_message(self) -> None:
        """Send welcome message to #general channel.

        Announces new worker and suggests using msgr to communicate.
        Silently fails if general channel doesn't exist or messaging fails.
        """
        try:
            from ..queries.channel import get_channel_by_name, create_message_with_notifications

            # Find general channel
            general = get_channel_by_name(self.worker.db, "general")
            if not general:
                # No general channel - skip welcome message
                return

            # Compose welcome message
            message = (
                f"Welcome {self.worker.name}! 👋\n\n"
                f"Role: {self.worker.role}\n"
                f"Team: {self.worker.team_id or 'Unassigned'}\n\n"
                f"Get started:\n"
                f"• Check your inbox: `msgr inbox`\n"
                f"• View available channels: `msgr channels`\n"
                f"• Read your briefing: `cat BRIEFING.md`\n\n"
                f"We're glad to have you on the team!"
            )

            # Send message to general channel (system message, no notifications)
            create_message_with_notifications(
                db=self.worker.db,
                channel_id=general.id,
                from_worker_id=self.worker.id,
                content=message,
                priority=3,  # Low priority (informational)
                time_sensitivity="whenever",
            )

        except Exception:
            # Silently fail - welcome message is nice-to-have, not critical
            pass

    def fail_onboarding(self) -> None:
        """Transition from onboarding to terminated (failed onboarding).

        Cleans up worker storage directory since worker never became active.
        Unlike normal termination, no review/archive is needed for failed onboarding.
        """
        old_status = self.worker.lifecycle_status
        self._validate_lifecycle_transition("terminated")

        # Clean up worker storage - no review needed for failed onboarding
        try:
            storage = self.worker._storage_mgr.get_storage_manager()
            storage.delete_worker_storage(self.worker.id)
        except WorkerStorageNotFound:
            # Storage doesn't exist yet - OK to continue
            pass

        update_worker_status(self.worker.db, self.worker.id, "terminated")
        self.worker._worker_data = None
        log_worker_lifecycle(_logger, self.worker.id, self.worker.name, old_status, "terminated")

    def start_offboarding(self) -> None:
        """Transition from active to offboarding.

        Per CLAUDE.md: "On fire: freeze -> ask bead for review -> teammate
        saves useful to shared/ -> delete."

        When entering OFFBOARDING state:
        1. Freeze worker storage (mark read-only)
        2. Create a review bead assigned to manager for work handoff

        The manager will review frozen storage and archive useful files
        before the worker is terminated.
        """
        old_status = self.worker.lifecycle_status
        self._validate_lifecycle_transition("offboarding")

        # Freeze worker storage for review (if exists)
        try:
            storage = self.worker._storage_mgr.get_storage_manager()
            storage.freeze_worker(self.worker.id)
        except (WorkerStorageNotFound, StorageAlreadyFrozen):
            # Storage doesn't exist or already frozen - OK to continue
            pass

        # Create review bead for manager if worker has a manager
        if self.worker.manager_id:
            self._create_offboarding_review_bead()

        update_worker_status(self.worker.db, self.worker.id, "offboarding")
        self.worker._worker_data = None
        log_worker_lifecycle(_logger, self.worker.id, self.worker.name, old_status, "offboarding")

    def _create_offboarding_review_bead(self) -> None:
        """Create a review notification bead for the manager.

        Uses MessagingService to create a direct channel between the
        offboarding worker and their manager, send a handoff message,
        and create a notification bead for the review.
        """
        if not self.worker.manager_id:
            return

        try:
            messaging = self.worker._get_messaging_service()
            result = messaging.send_offboarding_notification(
                worker_id=self.worker.id,
                worker_name=self.worker.name,
                worker_role=self.worker.role,
                manager_id=self.worker.manager_id,
            )
            # Result is best-effort - we don't raise on failure
            if not result.success:
                _logger.debug(f"Offboarding notification failed: {result.error}")
        except (ImportError, sqlite3.Error, ValueError) as e:
            # Intentionally swallowed: notification is best-effort during offboarding.
            # ImportError: messaging module not available
            # sqlite3.Error: database issues, ValueError: invalid data
            _logger.debug(f"Offboarding notification failed: {e}")
            pass

        # Also create an 'ask' bead for tracking the review workflow
        self._create_offboarding_ask_bead()

    def _create_offboarding_ask_bead(self) -> Optional[str]:
        """Create an 'ask' bead for offboarding storage review.

        Per README workflow:
        1. Worker folder frozen (read-only) - done in start_offboarding
        2. System creates 'ask' bead: 'Offboard storage review: {worker-id}'
        3. Assigned teammate reviews, moves useful -> shared/, deletes rest
        4. On ask completion, system deletes worker folder

        Returns:
            Created bead ID, or None if creation failed.
        """
        if not self.worker.manager_id:
            return None

        try:
            beads_client = self.worker._get_beads_client()

            # Create the 'ask' bead with metadata linking to worker
            result = beads_client.create(
                title=f"Offboard storage review: {self.worker.id}",
                type=BEAD_TYPE_ASK,
                priority="P1",  # High priority
                description=(
                    f"Review frozen storage for terminated worker {self.worker.name} "
                    f"({self.worker.id}).\n\n"
                    f"Role: {self.worker.role}\n\n"
                    f"Actions required:\n"
                    f"1. Review files in frozen storage\n"
                    f"2. Move useful files to shared/archive/{self.worker.id}/\n"
                    f"3. Close this bead when review is complete\n"
                    f"4. System will delete worker folder on bead closure"
                ),
                assignee=self.worker.manager_id,
                metadata={
                    "worker_id": self.worker.id,
                    "worker_name": self.worker.name,
                    "manager_id": self.worker.manager_id,
                    "workflow": "offboarding_storage_review",
                },
            )

            bead_id = result.bead_id if result.success else None
            if bead_id:
                # Store the bead ID in worker metadata for later lookup
                self._store_offboarding_ask_bead_id(bead_id)

            return bead_id

        except (BdCommandError, Exception):
            # Intentionally swallowed: bead creation is best-effort during offboarding.
            return None
        except (FileNotFoundError, OSError):
            # FileNotFoundError: bd CLI not installed
            # OSError: other file system issues with bd
            return None

    def _store_offboarding_ask_bead_id(self, bead_id: str) -> None:
        """Store the offboarding ask bead ID in worker metadata.

        Args:
            bead_id: The created bead ID
        """
        try:
            # Store in a metadata column or a separate table
            # For now, use worker_state's metadata or a simple approach
            now = datetime.now()
            self.worker.db.execute(
                """UPDATE workers
                   SET offboarding_ask_bead_id = ?, updated_at = ?
                   WHERE id = ?""",
                (bead_id, now, self.worker.id)
            )
            self.worker.db.connection.commit()

            # Publish OFFBOARDING_ASK_CREATED event
            try:
                from ..events import EventBus, EventType

                bus = EventBus(self.worker.db)
                bus.publish(
                    EventType.OFFBOARDING_ASK_CREATED,
                    "offboarding",
                    bead_id,
                    {
                        "worker_id": self.worker.id,
                        "worker_name": self.worker.name,
                        "manager_id": self.worker.manager_id,
                        "bead_id": bead_id,
                    },
                )
            except (ImportError, sqlite3.Error):
                # Intentionally swallowed: event publishing is best-effort.
                pass
        except sqlite3.Error:
            # Intentionally swallowed: storing bead ID is best-effort.
            pass

    def get_offboarding_ask_bead_id(self) -> Optional[str]:
        """Get the offboarding ask bead ID for this worker.

        Returns:
            The bead ID if set, None otherwise.
        """
        row = self.worker.db.fetchone(
            "SELECT offboarding_ask_bead_id FROM workers WHERE id = ?",
            (self.worker.id,)
        )
        if row and row["offboarding_ask_bead_id"]:
            return row["offboarding_ask_bead_id"]
        return None

    def suspend(self, force: bool = False) -> None:
        """Suspend worker - temporarily inactive.

        Transitions worker from 'active' to 'suspended'.
        Stops any active session and prevents new sessions from spawning.

        Args:
            force: If True, force stop session without graceful shutdown

        Raises:
            InvalidStateTransition: If not in 'active' state
        """
        old_status = self.worker.lifecycle_status

        # Validate transition
        self._validate_lifecycle_transition("suspended")

        # Stop session if running
        if self.worker.is_session_active:
            self.worker._session_mgr.stop_session(force=force)

        # Update lifecycle status
        update_worker_status(self.worker.db, self.worker.id, "suspended")
        log_worker_lifecycle(_logger, self.worker.id, self.worker.name, old_status, "suspended")

        self.worker._worker_data = None

    def unsuspend(self) -> None:
        """Resume suspended worker - return to active state.

        Transitions worker from 'suspended' to 'active'.
        Worker can then spawn sessions and accept work.

        Raises:
            InvalidStateTransition: If not in 'suspended' state
        """
        old_status = self.worker.lifecycle_status

        # Validate transition
        self._validate_lifecycle_transition("active")

        # Update lifecycle status
        update_worker_status(self.worker.db, self.worker.id, "active")
        log_worker_lifecycle(_logger, self.worker.id, self.worker.name, old_status, "active")

        self.worker._worker_data = None

    def terminate(self) -> None:
        """Terminate worker - freeze storage, update org-chart, fire event.

        Performs a full termination workflow:
        1. Stop session if running
        2. Freeze worker storage
        3. Unsubscribe from all channels
        4. Update lifecycle status to terminated
        5. Update org-chart
        6. Publish WORKER_FIRED event

        Raises:
            InvalidStateTransition: If not in a state that can transition to terminated
        """
        import subprocess

        old_status = self.worker.lifecycle_status

        # Stop session first if any
        self.worker._session_mgr.terminate_session(force=True)

        # Freeze worker storage for review (if exists)
        try:
            storage = self.worker._storage_mgr.get_storage_manager()
            storage.freeze_worker(self.worker.id)
        except (WorkerStorageNotFound, StorageAlreadyFrozen):
            # Storage doesn't exist or already frozen - OK to continue
            pass

        # Unsubscribe from all channels
        unsubscribe_from_all_channels(self.worker.db, self.worker.id)

        # Remove from all teams (org-chart sync)
        memberships = get_worker_team_memberships(self.worker.db, self.worker.id)
        for membership in memberships:
            remove_team_member(self.worker.db, membership.team_id, self.worker.id)

        # Validate and update lifecycle status
        self._validate_lifecycle_transition("terminated")
        update_worker_status(self.worker.db, self.worker.id, "terminated")
        log_worker_lifecycle(_logger, self.worker.id, self.worker.name, old_status, "terminated")

        # Update org-chart
        try:
            from ..org_chart import update_org_chart, git_commit_org_chart

            org_path = self.worker._storage_mgr.get_org_path()
            update_org_chart(self.worker.db, org_path)
            # Commit to git (best-effort, gracefully handles non-git repos)
            git_commit_org_chart(
                org_path=org_path,
                change_type="terminated",
                worker_name=self.worker.name,
                worker_role=self.worker.role,
            )
        except (ImportError, OSError, subprocess.SubprocessError):
            # Intentionally swallowed: org-chart update is best-effort.
            # ImportError: org_chart module not available
            # OSError: file system issues, SubprocessError: git command failed
            pass

        # Publish WORKER_FIRED event
        try:
            from ..events import EventBus, EventType

            bus = EventBus(self.worker.db)
            bus.publish(
                EventType.WORKER_FIRED,
                "worker",
                self.worker.id,
                {
                    "name": self.worker.name,
                    "role": self.worker.role,
                },
            )
        except (ImportError, sqlite3.Error):
            # Intentionally swallowed: event publishing is best-effort.
            pass

        self.worker._worker_data = None

"""
Worker termination cleanup functions.

Standalone functions for processing offboarding and cleanup of terminated workers.
These are separated from the Worker class as they operate on workers from outside
the worker instance itself (e.g., cron jobs, event handlers).
"""

import sqlite3
from pathlib import Path
from typing import Optional

from .db import Database
from .queries import get_worker
from .storage import StorageManager, WorkerStorageNotFound
from shared import WorkerNotFound
from shared.bd.client import BdClient, BdCommandError


def check_offboarding_ask_completed(
    db: Database,
    worker_id: str,
    bd_client: Optional[BdClient] = None,
) -> bool:
    """Check if the offboarding ask bead for a worker is completed.

    Per README workflow:
    1. Worker folder frozen (read-only)
    2. System creates 'ask' bead: 'Offboard storage review: {worker-id}'
    3. Assigned teammate reviews, moves useful -> shared/, deletes rest
    4. On ask completion, system deletes worker folder

    This function checks step 4 - whether the ask bead has been closed.

    Args:
        db: Database instance
        worker_id: Worker ID to check
        bd_client: Optional BdClient instance (creates default if None)

    Returns:
        True if ask bead is closed, False otherwise (or if no bead exists)
    """
    # Get the worker's offboarding ask bead ID
    row = db.fetchone(
        "SELECT offboarding_ask_bead_id FROM workers WHERE id = ?",
        (worker_id,)
    )

    if not row or not row["offboarding_ask_bead_id"]:
        return False

    bead_id = row["offboarding_ask_bead_id"]

    # Check bead status via bd client
    if bd_client is None:
        bd_client = BdClient()

    try:
        issue = bd_client.get_issue(bead_id)
        if issue and issue.get("status") == "closed":
            return True
    except BdCommandError:
        pass

    return False


def process_offboarding_cleanup(
    db: Database,
    worker_id: str,
    storage_manager: StorageManager,
    bd_client: Optional[BdClient] = None,
    files_to_archive: Optional[list[Path]] = None,
) -> Optional[dict]:
    """Process offboarding cleanup if the ask bead is completed.

    This is the hook that should be called (e.g., by a cron job or event handler)
    to check if a worker's offboarding review has been completed and trigger
    the storage cleanup.

    Per README workflow:
    1. Worker folder frozen (read-only) - already done
    2. System creates 'ask' bead - already done
    3. Assigned teammate reviews, moves useful -> shared/, deletes rest
    4. On ask completion, system deletes worker folder <- this function does this

    Args:
        db: Database instance
        worker_id: Worker ID to process
        storage_manager: StorageManager for the org
        bd_client: Optional BdClient instance
        files_to_archive: Optional list of files to archive (if None, archives all)

    Returns:
        Cleanup result dict if cleanup was performed, None if not ready
    """
    # Check if worker is in terminated state
    worker_data = get_worker(db, worker_id)
    if worker_data is None or worker_data.status != "terminated":
        return None

    # Check if the ask bead is completed
    if not check_offboarding_ask_completed(db, worker_id, bd_client):
        return None

    # Publish OFFBOARDING_ASK_COMPLETED event
    bead_id = db.fetchone(
        "SELECT offboarding_ask_bead_id FROM workers WHERE id = ?",
        (worker_id,)
    )
    if bead_id and bead_id["offboarding_ask_bead_id"]:
        try:
            from .events import EventBus, EventType

            bus = EventBus(db)
            bus.publish(
                EventType.OFFBOARDING_ASK_COMPLETED,
                "offboarding",
                bead_id["offboarding_ask_bead_id"],
                {
                    "worker_id": worker_id,
                    "bead_id": bead_id["offboarding_ask_bead_id"],
                },
            )
        except (ImportError, sqlite3.Error):
            # Intentionally swallowed: event publishing is best-effort.
            pass

    # Bead is completed - run cleanup
    result = cleanup_terminated_worker(
        db=db,
        worker_id=worker_id,
        storage_manager=storage_manager,
        files_to_archive=files_to_archive,
    )

    # Publish OFFBOARDING_CLEANUP_DONE event
    if result:
        try:
            from .events import EventBus, EventType

            bus = EventBus(db)
            bus.publish(
                EventType.OFFBOARDING_CLEANUP_DONE,
                "offboarding",
                worker_id,
                {
                    "worker_id": worker_id,
                    "files_archived": result.get("files_archived", 0),
                    "archived_to": result.get("archived_to"),
                    "storage_deleted": result.get("storage_deleted", False),
                },
            )
        except (ImportError, sqlite3.Error):
            # Intentionally swallowed: event publishing is best-effort.
            pass

    return result


def cleanup_terminated_worker(
    db: Database,
    worker_id: str,
    storage_manager: StorageManager,
    files_to_archive: Optional[list[Path]] = None,
) -> dict:
    """Clean up a terminated worker's data.

    Per CLAUDE.md: "On fire: freeze -> ask bead for review -> teammate
    saves useful to shared/ -> delete."

    This function completes the termination workflow:
    1. Archive useful files to shared/archive/{worker_id}/
    2. Delete worker session data (frozen storage)
    3. Keep worker record in DB (for audit trail)

    The worker must already be in TERMINATED state. Use Worker.terminate()
    to transition a worker to terminated state and freeze their storage.

    Args:
        db: Database instance
        worker_id: Worker ID to clean up
        storage_manager: StorageManager for the org
        files_to_archive: List of file paths to archive from worker storage.
                         If None, archives all files. Paths should be relative
                         to worker storage root.

    Returns:
        Dict with cleanup results:
        - archived_to: Path to archive directory (or None if no files)
        - files_archived: Number of files archived
        - storage_deleted: Whether storage was deleted

    Raises:
        WorkerNotFound: If worker doesn't exist
        ValueError: If worker is not in TERMINATED state

    Example:
        # After manager reviews frozen storage and identifies useful files
        result = cleanup_terminated_worker(
            db=db,
            worker_id="worker-abc123",
            storage_manager=storage,
            files_to_archive=[Path("important-doc.md"), Path("config.yaml")],
        )
        print(f"Archived {result['files_archived']} files to {result['archived_to']}")
    """
    # Verify worker exists and is terminated
    worker_data = get_worker(db, worker_id)
    if worker_data is None:
        raise WorkerNotFound(worker_id)

    if worker_data.status != "terminated":
        raise ValueError(
            f"Worker {worker_id} is not terminated (status: {worker_data.status}). "
            "Use Worker.terminate() first."
        )

    result = {
        "archived_to": None,
        "files_archived": 0,
        "storage_deleted": False,
    }

    # Archive files if storage exists
    try:
        # Get list of files that exist
        existing_files = storage_manager.list_worker_files(worker_id)

        if existing_files:
            # Archive specified files or all files
            archive_files = files_to_archive if files_to_archive is not None else existing_files
            archive_path = storage_manager.archive_worker_files(worker_id, archive_files)
            result["archived_to"] = str(archive_path)
            result["files_archived"] = len(archive_files)

        # Delete worker storage
        if storage_manager.delete_worker_storage(worker_id):
            result["storage_deleted"] = True

    except WorkerStorageNotFound:
        # No storage to clean up - that's OK
        pass

    return result

"""
Storage abstraction for QuinnAI CLI.

Manages worker and shared storage following the org-chart hierarchy.
Storage mirrors org-chart structure:
- shared/ = org lifetime (topics/teams, survives workers)
- workers/ = worker lifetime (mirrors hierarchy)
"""

import shutil
from pathlib import Path
from typing import Optional

from .db import Database
from .queries import get_worker
from shared.exceptions import StorageError
from .constants import (
    STORAGE_DIR,
    SHARED_DIR,
    WORKERS_DIR,
    FROZEN_SUFFIX,
    ARCHIVE_DIR,
    DEFAULT_SHARED_TOPICS,
)


class WorkerStorageNotFound(StorageError):
    """Worker storage directory does not exist."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        super().__init__(f"Storage not found for worker: {worker_id}")


class StorageAlreadyFrozen(StorageError):
    """Worker storage is already frozen."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        super().__init__(f"Storage already frozen for worker: {worker_id}")


class StorageManager:
    """
    Manages worker and shared storage.

    Storage mirrors org-chart:
    - shared/ = org lifetime (topics/teams)
    - workers/ = worker lifetime (mirrors hierarchy)

    Directory structure example:
        storage/
        |-- shared/              # Org lifetime (survives workers)
        |   |-- engineering/
        |   |-- legal/
        |   |-- company/
        |-- workers/             # Worker lifetime (mirrors org-chart)
            |-- ceo/
                |-- director-abc/
                |   |-- engineer-xyz/
                |-- manager-def/
    """

    def __init__(self, org_path: Path, db: Optional[Database] = None):
        """Initialize storage manager.

        Args:
            org_path: Path to the org folder
            db: Optional database instance for worker hierarchy lookup.
                Required for hierarchy-aware operations like get_worker_path.
        """
        self.org_path = org_path
        self.storage_root = org_path / STORAGE_DIR
        self.db = db

    def _get_worker_hierarchy_chain(self, worker_id: str) -> list[str]:
        """Get the chain of worker IDs from root to worker.

        Builds the hierarchy path by following manager_id up the tree.
        Returns list starting from root (CEO) to the target worker.

        Args:
            worker_id: Worker ID to get chain for

        Returns:
            List of worker IDs from root to worker, e.g.:
            ["ceo", "director-abc", "engineer-xyz"]

        Raises:
            WorkerStorageNotFound: If worker not found in database
            ValueError: If database not provided
        """
        if self.db is None:
            raise ValueError("Database required for hierarchy lookup")

        chain: list[str] = []
        current_id: Optional[str] = worker_id

        # Walk up the hierarchy collecting IDs
        visited: set[str] = set()  # Prevent infinite loops
        while current_id is not None:
            if current_id in visited:
                # Circular reference detected, break
                break
            visited.add(current_id)

            worker = get_worker(self.db, current_id)
            if worker is None:
                raise WorkerStorageNotFound(current_id)

            chain.append(current_id)
            current_id = worker.manager_id

        # Reverse so root is first
        chain.reverse()
        return chain

    def _build_path_from_reports_chain(
        self,
        worker_id: str,
        reports_to: str,
    ) -> Path:
        """Build worker path from reports_to, looking up parent chain from db if needed.

        When reports_to is provided, we need to find the full path for the parent.
        If the parent also has reports_to="" it's at root, otherwise we look it up.

        Args:
            worker_id: Worker ID
            reports_to: Manager worker ID

        Returns:
            Full path to worker storage
        """
        if reports_to == "":
            # Root worker (CEO)
            return self.storage_root / WORKERS_DIR / worker_id

        # We need to find the path for reports_to
        # If we have a database, use it to get the full chain
        if self.db is not None:
            # Get parent's full chain from DB
            parent_chain = self._get_worker_hierarchy_chain(reports_to)
            path = self.storage_root / WORKERS_DIR
            for wid in parent_chain:
                path = path / wid
            return path / worker_id
        else:
            # Without DB, we can only handle the case where reports_to is at root
            # Assume reports_to is at root - caller must ensure this is correct
            return self.storage_root / WORKERS_DIR / reports_to / worker_id

    def get_worker_path(
        self,
        worker_id: str,
        reports_to: Optional[str] = None,
    ) -> Path:
        """Get storage path for worker (mirrors org-chart hierarchy).

        If reports_to is provided, uses that directly. Otherwise looks up
        the full hierarchy chain from the database.

        Examples:
            - CEO: storage/workers/ceo/
            - Director under CEO: storage/workers/ceo/director-{id}/
            - Engineer under Director: storage/workers/ceo/director-{id}/engineer-{id}/

        Args:
            worker_id: Worker ID
            reports_to: Optional manager worker ID (if known). When provided,
                        skips database lookup and builds path directly.
                        Use empty string "" for root workers (CEO).

        Returns:
            Path to worker's storage directory

        Raises:
            WorkerStorageNotFound: If worker not in database (when reports_to not provided)
            ValueError: If database not provided and reports_to not specified
        """
        if reports_to is not None:
            return self._build_path_from_reports_chain(worker_id, reports_to)

        # Look up full hierarchy from database
        chain = self._get_worker_hierarchy_chain(worker_id)

        # Build path from chain
        path = self.storage_root / WORKERS_DIR
        for wid in chain:
            path = path / wid

        return path

    def get_shared_path(self, topic: str) -> Path:
        """Get shared storage path for topic.

        Args:
            topic: Topic name (e.g., "engineering", "legal", "company")

        Returns:
            Path to shared topic directory (storage/shared/{topic}/)
        """
        return self.storage_root / SHARED_DIR / topic

    def ensure_worker_storage(
        self,
        worker_id: str,
        reports_to: Optional[str] = None,
    ) -> Path:
        """Create worker storage directory if not exists.

        Args:
            worker_id: Worker ID
            reports_to: Optional manager worker ID

        Returns:
            Path to created/existing worker storage directory
        """
        path = self.get_worker_path(worker_id, reports_to)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_shared_storage(self, topic: str) -> Path:
        """Create shared storage directory if not exists.

        Args:
            topic: Topic name

        Returns:
            Path to created/existing shared storage directory
        """
        path = self.get_shared_path(topic)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def initialize_storage(self) -> None:
        """Initialize storage structure with default directories.

        Creates:
        - storage/shared/ with default topics
        - storage/workers/
        """
        # Create shared directories
        for topic in DEFAULT_SHARED_TOPICS:
            self.ensure_shared_storage(topic)

        # Create workers root directory
        workers_root = self.storage_root / WORKERS_DIR
        workers_root.mkdir(parents=True, exist_ok=True)

    def worker_storage_exists(
        self,
        worker_id: str,
        reports_to: Optional[str] = None,
    ) -> bool:
        """Check if worker storage exists.

        Args:
            worker_id: Worker ID
            reports_to: Optional manager worker ID

        Returns:
            True if storage directory exists
        """
        path = self.get_worker_path(worker_id, reports_to)
        return path.exists() and path.is_dir()

    def is_worker_frozen(
        self,
        worker_id: str,
        reports_to: Optional[str] = None,
    ) -> bool:
        """Check if worker storage is frozen.

        Args:
            worker_id: Worker ID
            reports_to: Optional manager worker ID

        Returns:
            True if storage is frozen (has .frozen suffix)
        """
        path = self.get_worker_path(worker_id, reports_to)
        frozen_path = path.parent / f"{path.name}{FROZEN_SUFFIX}"
        return frozen_path.exists()

    def freeze_worker(
        self,
        worker_id: str,
        reports_to: Optional[str] = None,
    ) -> Path:
        """Freeze worker storage on termination.

        Renames worker storage directory with .frozen suffix to mark it
        as archived and prevent accidental modifications.

        Args:
            worker_id: Worker ID
            reports_to: Optional manager worker ID

        Returns:
            Path to frozen storage directory

        Raises:
            WorkerStorageNotFound: If worker storage doesn't exist
            StorageAlreadyFrozen: If storage is already frozen
        """
        path = self.get_worker_path(worker_id, reports_to)
        frozen_path = path.parent / f"{path.name}{FROZEN_SUFFIX}"

        # Check if already frozen FIRST (before checking if original exists)
        if frozen_path.exists():
            raise StorageAlreadyFrozen(worker_id)

        if not path.exists():
            raise WorkerStorageNotFound(worker_id)

        path.rename(frozen_path)
        return frozen_path

    def unfreeze_worker(
        self,
        worker_id: str,
        reports_to: Optional[str] = None,
    ) -> Path:
        """Unfreeze worker storage (restore from frozen state).

        Args:
            worker_id: Worker ID
            reports_to: Optional manager worker ID

        Returns:
            Path to restored storage directory

        Raises:
            WorkerStorageNotFound: If frozen storage doesn't exist
        """
        path = self.get_worker_path(worker_id, reports_to)
        frozen_path = path.parent / f"{path.name}{FROZEN_SUFFIX}"

        if not frozen_path.exists():
            raise WorkerStorageNotFound(worker_id)

        frozen_path.rename(path)
        return path

    def get_archive_path(self, worker_id: str) -> Path:
        """Get shared archive path for a terminated worker.

        Per CLAUDE.md: "On fire: freeze -> ask bead for review -> teammate
        saves useful to shared/ -> delete."

        Args:
            worker_id: Worker ID

        Returns:
            Path to shared/archive/{worker_id}/
        """
        return self.storage_root / SHARED_DIR / ARCHIVE_DIR / worker_id

    def archive_worker_files(
        self,
        worker_id: str,
        files: Optional[list[Path]] = None,
        reports_to: Optional[str] = None,
    ) -> Path:
        """Archive worker files to shared/archive/{worker_id}/.

        Copies specified files (or all files if none specified) from worker
        storage to the shared archive. Used during termination cleanup.

        Args:
            worker_id: Worker ID
            files: List of file paths to archive. If None, archives all files.
                  Paths should be relative to worker storage root.
            reports_to: Optional manager worker ID

        Returns:
            Path to the archive directory

        Raises:
            WorkerStorageNotFound: If worker storage doesn't exist
        """
        path = self.get_worker_path(worker_id, reports_to)

        # Check both normal and frozen paths
        frozen_path = path.parent / f"{path.name}{FROZEN_SUFFIX}"
        actual_path = frozen_path if frozen_path.exists() else path

        if not actual_path.exists():
            raise WorkerStorageNotFound(worker_id)

        # Create archive directory
        archive_path = self.get_archive_path(worker_id)
        archive_path.mkdir(parents=True, exist_ok=True)

        # Get files to archive
        if files is None:
            files = self.list_worker_files(worker_id, reports_to)

        # Copy files to archive
        for file_path in files:
            if file_path.is_absolute():
                source = file_path
                rel_path = file_path.name
            else:
                source = actual_path / file_path
                rel_path = file_path

            if source.exists() and source.is_file():
                dest = archive_path / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)

                # Handle name conflicts
                if dest.exists():
                    counter = 1
                    stem = dest.stem
                    suffix = dest.suffix
                    parent = dest.parent
                    while dest.exists():
                        dest = parent / f"{stem}_{counter}{suffix}"
                        counter += 1

                shutil.copy2(source, dest)

        return archive_path

    def delete_worker_storage(
        self,
        worker_id: str,
        reports_to: Optional[str] = None,
    ) -> bool:
        """Delete worker storage directory.

        Removes the worker's storage directory (frozen or unfrozen).
        Used after archiving useful files during termination cleanup.

        Args:
            worker_id: Worker ID
            reports_to: Optional manager worker ID

        Returns:
            True if deleted, False if storage didn't exist
        """
        path = self.get_worker_path(worker_id, reports_to)

        # Check both normal and frozen paths
        frozen_path = path.parent / f"{path.name}{FROZEN_SUFFIX}"

        if frozen_path.exists():
            shutil.rmtree(frozen_path)
            return True
        elif path.exists():
            shutil.rmtree(path)
            return True

        return False

    def cleanup_worker(
        self,
        worker_id: str,
        useful_files: Optional[list[Path]] = None,
        target_topic: str = "company",
        reports_to: Optional[str] = None,
    ) -> None:
        """Move useful files to shared, delete worker folder.

        This is the final cleanup after a worker is terminated and their
        work has been reviewed. Useful files are moved to shared storage
        for team access, then the worker folder is deleted.

        Args:
            worker_id: Worker ID
            useful_files: List of file paths within worker storage to preserve.
                         Paths should be relative to worker storage root.
            target_topic: Shared topic to move files to (default: "company")
            reports_to: Optional manager worker ID

        Raises:
            WorkerStorageNotFound: If worker storage doesn't exist
        """
        path = self.get_worker_path(worker_id, reports_to)

        # Check both normal and frozen paths
        frozen_path = path.parent / f"{path.name}{FROZEN_SUFFIX}"
        actual_path = frozen_path if frozen_path.exists() else path

        if not actual_path.exists():
            raise WorkerStorageNotFound(worker_id)

        # Move useful files to shared storage
        if useful_files:
            shared_path = self.ensure_shared_storage(target_topic)
            worker_archive = shared_path / f"from-{worker_id}"
            worker_archive.mkdir(parents=True, exist_ok=True)

            for file_path in useful_files:
                # Handle both absolute and relative paths
                if file_path.is_absolute():
                    source = file_path
                else:
                    source = actual_path / file_path

                if source.exists():
                    dest = worker_archive / file_path.name
                    # Handle name conflicts
                    counter = 1
                    while dest.exists():
                        stem = file_path.stem
                        suffix = file_path.suffix
                        dest = worker_archive / f"{stem}_{counter}{suffix}"
                        counter += 1

                    shutil.copy2(source, dest)

        # Delete the worker folder
        shutil.rmtree(actual_path)

    def list_worker_files(
        self,
        worker_id: str,
        reports_to: Optional[str] = None,
    ) -> list[Path]:
        """List all files in worker storage.

        Args:
            worker_id: Worker ID
            reports_to: Optional manager worker ID

        Returns:
            List of file paths (relative to worker storage root)

        Raises:
            WorkerStorageNotFound: If worker storage doesn't exist
        """
        path = self.get_worker_path(worker_id, reports_to)

        # Check frozen path as fallback
        if not path.exists():
            frozen_path = path.parent / f"{path.name}{FROZEN_SUFFIX}"
            if frozen_path.exists():
                path = frozen_path
            else:
                raise WorkerStorageNotFound(worker_id)

        files: list[Path] = []
        for item in path.rglob("*"):
            if item.is_file():
                files.append(item.relative_to(path))

        return sorted(files)

    def get_storage_stats(self) -> dict:
        """Get storage statistics.

        Returns:
            Dict with storage statistics:
            - total_workers: Number of worker storage dirs
            - frozen_workers: Number of frozen worker dirs
            - shared_topics: List of shared topic names
            - total_size_bytes: Total storage size in bytes
        """
        stats = {
            "total_workers": 0,
            "frozen_workers": 0,
            "shared_topics": [],
            "total_size_bytes": 0,
        }

        # Count worker directories
        workers_root = self.storage_root / WORKERS_DIR
        if workers_root.exists():
            for item in workers_root.rglob("*"):
                if item.is_dir():
                    if item.name.endswith(FROZEN_SUFFIX):
                        stats["frozen_workers"] += 1
                    else:
                        stats["total_workers"] += 1
                if item.is_file():
                    stats["total_size_bytes"] += item.stat().st_size

        # List shared topics
        shared_root = self.storage_root / SHARED_DIR
        if shared_root.exists():
            for item in shared_root.iterdir():
                if item.is_dir():
                    stats["shared_topics"].append(item.name)
                    # Add shared files to total size
                    for file in item.rglob("*"):
                        if file.is_file():
                            stats["total_size_bytes"] += file.stat().st_size

        return stats

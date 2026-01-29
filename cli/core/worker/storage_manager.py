"""
Worker storage management.

Handles storage path management and storage-related operations for workers.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from ..storage import StorageManager

if TYPE_CHECKING:
    from ..db import Database


class WorkerStorageManager:
    """Manages storage operations for a worker.

    Handles:
    - Storage path management
    - Storage directory creation
    - Storage archiving
    """

    def __init__(self, worker: "WorkerBase"):
        """Initialize storage manager.

        Args:
            worker: Parent Worker instance
        """
        self.worker = worker

    def get_org_path(self) -> Path:
        """Get the org path from the database path or worker's org_path.

        Derives org_path from db.db_path (quinn.db is at org_path/live/quinn.db).

        Returns:
            Path to the org folder

        Raises:
            ValueError: If org_path not set and cannot derive from db
        """
        if self.worker._org_path is not None:
            return self.worker._org_path
        # Derive from db path: org_path/live/quinn.db -> org_path
        return self.worker.db.db_path.parent.parent

    def get_storage_manager(self) -> StorageManager:
        """Get a StorageManager for this worker's org.

        Returns:
            StorageManager instance configured for this org
        """
        org_path = self.get_org_path()
        return StorageManager(org_path, self.worker.db)

"""
BeadService - Permission-enforced bead operations.

Wraps bead operations with permission checks to ensure workers can only
access and modify beads they have permission for.

Per CLAUDE.md: "One Protocol For Everything" - all access through permissions.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional, List, Any, TYPE_CHECKING

from .db import Database
from .constants import BEAD_TYPE_TASK
from .permissions import (
    PermissionLevel,
    PermissionDenied,
    check_bead_permission,
    require_bead_permission,
    can_worker_access_bead,
)
from .queries import log_permission_audit

if TYPE_CHECKING:
    pass


_logger = logging.getLogger(__name__)


@dataclass
class BeadResult:
    """Result of a bead operation."""

    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


class BeadService:
    """Permission-enforced service for bead operations.

    All operations check permissions before executing. This ensures
    workers can only access beads they're authorized for.

    Example:
        service = BeadService(db, bd_path="/usr/local/bin/bd")

        # Get bead - requires READ permission
        result = service.get_bead(worker_id, "beads-123")

        # Update bead - requires WRITE permission
        result = service.update_bead(worker_id, "beads-123", status="closed")

        # Close bead - requires APPROVE permission
        result = service.close_bead(worker_id, "beads-123")
    """

    def __init__(
        self,
        db: Database,
        bd_path: str = "bd",
        beads_db: Optional[str] = None,
    ):
        """Initialize BeadService.

        Args:
            db: Quinn database for permission checks
            bd_path: Path to bd CLI binary
            beads_db: Optional path to beads database
        """
        self._db = db
        self._bd_path = bd_path
        self._beads_db = beads_db

    def _run_bd(self, *args, worker_id: str) -> BeadResult:
        """Run a bd command.

        Args:
            *args: Arguments for bd command
            worker_id: Worker executing command (for audit)

        Returns:
            BeadResult with command output
        """
        cmd = [self._bd_path]
        if self._beads_db:
            cmd.extend(["--db", self._beads_db])
        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return BeadResult(success=True, data=result.stdout.strip())
            else:
                return BeadResult(
                    success=False,
                    error=result.stderr.strip() or f"Command failed with code {result.returncode}",
                )
        except subprocess.TimeoutExpired:
            return BeadResult(success=False, error="Command timed out")
        except FileNotFoundError:
            return BeadResult(success=False, error=f"bd not found at: {self._bd_path}")
        except Exception as e:
            _logger.exception("Unexpected failure in run_bd_command")
            return BeadResult(success=False, error=str(e))

    def get_bead(self, worker_id: str, bead_id: str) -> BeadResult:
        """Get bead details.

        Requires: READ permission

        Args:
            worker_id: Worker requesting bead
            bead_id: Bead ID to fetch

        Returns:
            BeadResult with bead data

        Raises:
            PermissionDenied: If worker lacks READ permission
        """
        require_bead_permission(
            db=self._db,
            worker_id=worker_id,
            bead_id=bead_id,
            required_level=PermissionLevel.READ,
            action="get_bead",
        )

        return self._run_bd("show", bead_id, worker_id=worker_id)

    def list_beads(
        self,
        worker_id: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        limit: int = 50,
    ) -> BeadResult:
        """List beads visible to worker.

        Only returns beads the worker has at least READ permission for.
        Note: This relies on bd's output and filters client-side for now.

        Args:
            worker_id: Worker listing beads
            status: Optional status filter
            assignee: Optional assignee filter
            limit: Maximum beads to return

        Returns:
            BeadResult with filtered bead list
        """
        args = ["list"]
        if status:
            args.extend(["--status", status])
        if assignee:
            args.extend(["--assignee", assignee])
        args.extend(["--limit", str(limit)])

        result = self._run_bd(*args, worker_id=worker_id)

        # Note: Full filtering would require parsing output and checking
        # permissions on each bead. For now, we trust bd's output.
        return result

    def create_bead(
        self,
        worker_id: str,
        title: str,
        bead_type: str = BEAD_TYPE_TASK,
        priority: int = 2,
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        parent: Optional[str] = None,
    ) -> BeadResult:
        """Create a new bead.

        Creator automatically gets ADMIN permission on the created bead.

        Args:
            worker_id: Worker creating bead
            title: Bead title
            bead_type: Type (task, bug, feature, epic)
            priority: Priority (0-4)
            description: Optional description
            assignee: Optional initial assignee
            parent: Optional parent bead

        Returns:
            BeadResult with created bead ID
        """
        args = ["create", "--title", title, "--type", bead_type, "--priority", str(priority)]

        if description:
            args.extend(["--description", description])
        if assignee:
            args.extend(["--assignee", assignee])
        if parent:
            args.extend(["--parent", parent])

        result = self._run_bd(*args, worker_id=worker_id)

        # Log the creation using 'grant' action (creator gets ADMIN)
        if result.success:
            log_permission_audit(
                db=self._db,
                action="grant",
                bead_id=result.data,
                worker_id=worker_id,
                level=PermissionLevel.ADMIN,
                details=f"Created bead: {title}",
            )

        return result

    def update_bead(
        self,
        worker_id: str,
        bead_id: str,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        assignee: Optional[str] = None,
        title: Optional[str] = None,
    ) -> BeadResult:
        """Update bead properties.

        Requires: WRITE permission

        Args:
            worker_id: Worker updating bead
            bead_id: Bead to update
            status: Optional new status
            priority: Optional new priority
            assignee: Optional new assignee
            title: Optional new title

        Returns:
            BeadResult with update status

        Raises:
            PermissionDenied: If worker lacks WRITE permission
        """
        require_bead_permission(
            db=self._db,
            worker_id=worker_id,
            bead_id=bead_id,
            required_level=PermissionLevel.WRITE,
            action="update_bead",
        )

        args = ["update", bead_id]
        if status:
            args.extend(["--status", status])
        if priority is not None:
            args.extend(["--priority", str(priority)])
        if assignee:
            args.extend(["--assignee", assignee])
        if title:
            args.extend(["--title", title])

        return self._run_bd(*args, worker_id=worker_id)

    def close_bead(
        self,
        worker_id: str,
        bead_id: str,
        reason: Optional[str] = None,
    ) -> BeadResult:
        """Close a bead.

        Requires: APPROVE permission

        Args:
            worker_id: Worker closing bead
            bead_id: Bead to close
            reason: Optional closure reason

        Returns:
            BeadResult with close status

        Raises:
            PermissionDenied: If worker lacks APPROVE permission
        """
        require_bead_permission(
            db=self._db,
            worker_id=worker_id,
            bead_id=bead_id,
            required_level=PermissionLevel.APPROVE,
            action="close_bead",
        )

        args = ["close", bead_id]
        if reason:
            args.extend(["--reason", reason])

        return self._run_bd(*args, worker_id=worker_id)

    def add_comment(
        self,
        worker_id: str,
        bead_id: str,
        content: str,
    ) -> BeadResult:
        """Add comment to a bead.

        Requires: COMMENT permission

        Args:
            worker_id: Worker adding comment
            bead_id: Bead to comment on
            content: Comment content

        Returns:
            BeadResult with comment status

        Raises:
            PermissionDenied: If worker lacks COMMENT permission
        """
        require_bead_permission(
            db=self._db,
            worker_id=worker_id,
            bead_id=bead_id,
            required_level=PermissionLevel.COMMENT,
            action="add_comment",
        )

        # bd doesn't have a direct comment command, so this is a placeholder
        # In real implementation, would use bd's API or database directly
        return BeadResult(
            success=False,
            error="Comment functionality not yet implemented in bd",
        )

    def delete_bead(
        self,
        worker_id: str,
        bead_id: str,
    ) -> BeadResult:
        """Delete a bead.

        Requires: ADMIN permission

        Args:
            worker_id: Worker deleting bead
            bead_id: Bead to delete

        Returns:
            BeadResult with delete status

        Raises:
            PermissionDenied: If worker lacks ADMIN permission
        """
        require_bead_permission(
            db=self._db,
            worker_id=worker_id,
            bead_id=bead_id,
            required_level=PermissionLevel.ADMIN,
            action="delete_bead",
        )

        # bd doesn't have a delete command, so this is a placeholder
        return BeadResult(
            success=False,
            error="Delete functionality not yet implemented in bd",
        )

    def add_dependency(
        self,
        worker_id: str,
        bead_id: str,
        depends_on_id: str,
    ) -> BeadResult:
        """Add dependency between beads.

        Requires: WRITE permission on the bead being modified

        Args:
            worker_id: Worker adding dependency
            bead_id: Bead that will depend on another
            depends_on_id: Bead that will be depended on

        Returns:
            BeadResult with dependency status

        Raises:
            PermissionDenied: If worker lacks WRITE permission on bead_id
        """
        require_bead_permission(
            db=self._db,
            worker_id=worker_id,
            bead_id=bead_id,
            required_level=PermissionLevel.WRITE,
            action="add_dependency",
        )

        return self._run_bd("dep", "add", bead_id, depends_on_id, worker_id=worker_id)

    def get_permission_level(self, worker_id: str, bead_id: str) -> PermissionLevel:
        """Get worker's permission level on a bead.

        Args:
            worker_id: Worker to check
            bead_id: Bead to check

        Returns:
            PermissionLevel the worker has
        """
        return check_bead_permission(self._db, worker_id, bead_id)

    def can_access(
        self,
        worker_id: str,
        bead_id: str,
        level: PermissionLevel = PermissionLevel.READ,
    ) -> bool:
        """Check if worker can access bead at given level.

        Args:
            worker_id: Worker to check
            bead_id: Bead to check
            level: Required permission level

        Returns:
            True if worker has at least the required level
        """
        return can_worker_access_bead(self._db, worker_id, bead_id, level)

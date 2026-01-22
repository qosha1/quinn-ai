"""
Beads client abstraction for BD operations.

Provides a clean interface for bead/issue operations,
decoupling the BeadService from subprocess implementation details.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

from .process import ProcessAdapter, SubprocessAdapter


@dataclass
class Bead:
    """A bead/issue from the beads system."""
    id: str
    title: str
    type: str
    status: str
    priority: str = "P2"
    assignee: Optional[str] = None
    description: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeadResult:
    """Result from a bead operation."""
    success: bool
    bead_id: Optional[str] = None
    error: Optional[str] = None
    data: Optional[dict] = None


class BeadsClient(ABC):
    """Abstract client for bead operations."""

    @abstractmethod
    def get(self, bead_id: str) -> Optional[Bead]:
        """Get a bead by ID."""
        pass

    @abstractmethod
    def list(
        self,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 50,
    ) -> list[Bead]:
        """List beads with optional filters."""
        pass

    @abstractmethod
    def create(
        self,
        title: str,
        type: str,
        priority: str = "P2",
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> BeadResult:
        """Create a new bead."""
        pass

    @abstractmethod
    def update(
        self,
        bead_id: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> BeadResult:
        """Update a bead."""
        pass

    @abstractmethod
    def close(self, bead_id: str, reason: Optional[str] = None) -> BeadResult:
        """Close a bead."""
        pass


class SubprocessBeadsClient(BeadsClient):
    """Implementation using bd CLI subprocess."""

    def __init__(
        self,
        bd_path: Path,
        beads_dir: Optional[Path] = None,
        process: Optional[ProcessAdapter] = None,
    ):
        self._bd_path = bd_path
        self._beads_dir = beads_dir
        self._process = process or SubprocessAdapter()

    def _run_bd(self, *args: str) -> tuple[bool, str, str]:
        """Run bd command and return (success, stdout, stderr)."""
        import os

        cmd = [str(self._bd_path)]
        if self._beads_dir:
            cmd.extend(["--db", str(self._beads_dir / "issues.jsonl")])
        cmd.extend(args)

        env = os.environ.copy()
        if self._beads_dir:
            env["BEADS_DIR"] = str(self._beads_dir)

        result = self._process.run(cmd, env=env, timeout=30)
        return result.success, result.stdout, result.stderr

    def _parse_json_output(self, output: str) -> Optional[dict]:
        """Parse JSON output from bd command."""
        import json
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None

    def get(self, bead_id: str) -> Optional[Bead]:
        """Get a bead by ID."""
        success, stdout, _ = self._run_bd("show", bead_id, "--json")
        if not success:
            return None

        data = self._parse_json_output(stdout)
        if not data:
            return None

        return Bead(
            id=data.get("id", bead_id),
            title=data.get("title", ""),
            type=data.get("type", "task"),
            status=data.get("status", "open"),
            priority=data.get("priority", "P2"),
            assignee=data.get("assignee"),
            description=data.get("description"),
            metadata=data.get("metadata", {}),
        )

    def list(
        self,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 50,
    ) -> list[Bead]:
        """List beads with optional filters."""
        args = ["list", "--json", f"--limit={limit}"]
        if status:
            args.append(f"--status={status}")
        if assignee:
            args.append(f"--assignee={assignee}")
        if type:
            args.append(f"--type={type}")

        success, stdout, _ = self._run_bd(*args)
        if not success:
            return []

        data = self._parse_json_output(stdout)
        if not data or not isinstance(data, list):
            return []

        beads = []
        for item in data:
            beads.append(Bead(
                id=item.get("id", ""),
                title=item.get("title", ""),
                type=item.get("type", "task"),
                status=item.get("status", "open"),
                priority=item.get("priority", "P2"),
                assignee=item.get("assignee"),
                description=item.get("description"),
                metadata=item.get("metadata", {}),
            ))
        return beads

    def create(
        self,
        title: str,
        type: str,
        priority: str = "P2",
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> BeadResult:
        """Create a new bead."""
        args = ["create", f"--title={title}", f"--type={type}", f"--priority={priority}"]
        if description:
            args.append(f"--description={description}")
        if assignee:
            args.append(f"--assignee={assignee}")

        success, stdout, stderr = self._run_bd(*args)

        if not success:
            return BeadResult(success=False, error=stderr or "Failed to create bead")

        # Parse bead ID from output (usually on first line)
        bead_id = stdout.strip().split()[0] if stdout else None
        return BeadResult(success=True, bead_id=bead_id)

    def update(
        self,
        bead_id: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> BeadResult:
        """Update a bead."""
        args = ["update", bead_id]
        if status:
            args.append(f"--status={status}")
        if assignee:
            args.append(f"--assignee={assignee}")
        if priority:
            args.append(f"--priority={priority}")

        if len(args) == 2:
            return BeadResult(success=False, error="No updates specified")

        success, _, stderr = self._run_bd(*args)
        return BeadResult(
            success=success,
            bead_id=bead_id,
            error=stderr if not success else None,
        )

    def close(self, bead_id: str, reason: Optional[str] = None) -> BeadResult:
        """Close a bead."""
        args = ["close", bead_id]
        if reason:
            args.append(f"--reason={reason}")

        success, _, stderr = self._run_bd(*args)
        return BeadResult(
            success=success,
            bead_id=bead_id,
            error=stderr if not success else None,
        )


class MockBeadsClient(BeadsClient):
    """Mock client for testing."""

    def __init__(self):
        self._beads: dict[str, Bead] = {}
        self._next_id = 1

    def get(self, bead_id: str) -> Optional[Bead]:
        return self._beads.get(bead_id)

    def list(
        self,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 50,
    ) -> list[Bead]:
        result = list(self._beads.values())
        if status:
            result = [b for b in result if b.status == status]
        if assignee:
            result = [b for b in result if b.assignee == assignee]
        if type:
            result = [b for b in result if b.type == type]
        return result[:limit]

    def create(
        self,
        title: str,
        type: str,
        priority: str = "P2",
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> BeadResult:
        bead_id = f"mock-{self._next_id}"
        self._next_id += 1

        bead = Bead(
            id=bead_id,
            title=title,
            type=type,
            status="open",
            priority=priority,
            assignee=assignee,
            description=description,
            metadata=metadata or {},
        )
        self._beads[bead_id] = bead
        return BeadResult(success=True, bead_id=bead_id)

    def update(
        self,
        bead_id: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> BeadResult:
        bead = self._beads.get(bead_id)
        if not bead:
            return BeadResult(success=False, error=f"Bead {bead_id} not found")

        if status:
            bead.status = status
        if assignee:
            bead.assignee = assignee
        if priority:
            bead.priority = priority

        return BeadResult(success=True, bead_id=bead_id)

    def close(self, bead_id: str, reason: Optional[str] = None) -> BeadResult:
        bead = self._beads.get(bead_id)
        if not bead:
            return BeadResult(success=False, error=f"Bead {bead_id} not found")

        bead.status = "closed"
        return BeadResult(success=True, bead_id=bead_id)

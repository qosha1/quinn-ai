"""
OrgTopology loader from beads/quinn.db.

Loads organizational hierarchy from database and provides
traversal methods for escalation routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import subprocess

from shared.wrkr.escalation.hierarchical import (
    OrgTopology,
    WorkerNode,
    create_simple_topology,
)


@dataclass
class OrgWorker:
    """
    Extended worker information from the org-chart.

    Includes additional fields beyond WorkerNode for org management.

    Attributes:
        id: Unique worker identifier.
        name: Display name.
        boss_id: ID of direct supervisor (None = reports to board).
        is_manager: Whether this worker manages others.
        role_id: Role/position identifier.
        team_id: Team this worker belongs to.
        skills: Skill ratings dict.
        cost: Cost tier (0-100).
    """

    id: str
    name: str
    boss_id: str | None = None
    is_manager: bool = False
    role_id: str = ""
    team_id: str | None = None
    skills: dict[str, int] | None = None
    cost: int = 50


class BeadsOrgLoader:
    """
    Loads organizational hierarchy from beads.

    Workers are stored as issues with type "worker" in beads.
    The org chart is reconstructed from boss_id relationships.
    """

    def __init__(
        self,
        bd_command: str = "bd",
        db_path: str | None = None,
    ):
        """
        Initialize the org loader.

        Args:
            bd_command: Path to bd command.
            db_path: Optional database path override.
        """
        self._bd_command = bd_command
        self._db_path = db_path

    def _run_bd(self, *args: str) -> str:
        """Run a bd command and return output."""
        cmd = [self._bd_command] + list(args)
        if self._db_path:
            cmd.extend(["--db", self._db_path])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"bd command failed: {result.stderr}")
        return result.stdout

    def _parse_worker(self, issue: dict[str, Any]) -> OrgWorker:
        """Convert beads issue to OrgWorker."""
        metadata = issue.get("metadata", {})
        return OrgWorker(
            id=issue["id"],
            name=issue.get("title", ""),
            boss_id=metadata.get("boss_id"),
            is_manager=metadata.get("is_manager", False),
            role_id=metadata.get("role_id", ""),
            team_id=metadata.get("team_id"),
            skills=metadata.get("skills"),
            cost=metadata.get("cost", 50),
        )

    def load_workers(self) -> list[OrgWorker]:
        """
        Load all workers from beads.

        Returns:
            List of OrgWorker instances.
        """
        try:
            output = self._run_bd("list", "--json", "--type=worker", "--status=open")
            issues = json.loads(output) if output.strip() else []
        except (RuntimeError, json.JSONDecodeError):
            return []

        return [self._parse_worker(i) for i in issues]

    def load_topology(self) -> OrgTopology:
        """
        Load org topology from beads.

        Returns:
            OrgTopology populated with workers from beads.
        """
        workers = self.load_workers()

        # Convert to simple dict format for create_simple_topology
        worker_dicts = [
            {
                "id": w.id,
                "name": w.name,
                "boss_id": w.boss_id,
            }
            for w in workers
        ]

        return create_simple_topology(worker_dicts)

    def get_worker(self, worker_id: str) -> OrgWorker | None:
        """
        Get a specific worker by ID.

        Args:
            worker_id: The worker ID to retrieve.

        Returns:
            OrgWorker, or None if not found.
        """
        try:
            output = self._run_bd("show", worker_id, "--json")
            issue = json.loads(output)
        except (RuntimeError, json.JSONDecodeError):
            return None

        if issue.get("type") != "worker":
            return None

        return self._parse_worker(issue)

    def get_team_members(self, team_id: str) -> list[OrgWorker]:
        """
        Get all workers in a team.

        Args:
            team_id: The team ID to query.

        Returns:
            List of workers in the team.
        """
        workers = self.load_workers()
        return [w for w in workers if w.team_id == team_id]


class InMemoryOrgLoader:
    """
    In-memory org loader for testing.
    """

    def __init__(self):
        """Initialize empty org store."""
        self._workers: dict[str, OrgWorker] = {}

    def add_worker(self, worker: OrgWorker) -> None:
        """Add a worker to the store."""
        self._workers[worker.id] = worker

    def add_workers(self, workers: list[OrgWorker]) -> None:
        """Add multiple workers to the store."""
        for worker in workers:
            self._workers[worker.id] = worker

    def load_workers(self) -> list[OrgWorker]:
        """Load all workers."""
        return list(self._workers.values())

    def load_topology(self) -> OrgTopology:
        """Load org topology."""
        worker_dicts = [
            {
                "id": w.id,
                "name": w.name,
                "boss_id": w.boss_id,
            }
            for w in self._workers.values()
        ]
        return create_simple_topology(worker_dicts)

    def get_worker(self, worker_id: str) -> OrgWorker | None:
        """Get a specific worker."""
        return self._workers.get(worker_id)

    def get_team_members(self, team_id: str) -> list[OrgWorker]:
        """Get workers in a team."""
        return [w for w in self._workers.values() if w.team_id == team_id]


def build_standard_topology() -> tuple[OrgTopology, dict[str, OrgWorker]]:
    """
    Build a standard org topology for testing/demo.

    Creates a typical hierarchy:
    - Board (human oversight)
    - CEO
    - Directors (Engineering, Product)
    - Managers
    - Workers

    Returns:
        Tuple of (OrgTopology, dict of worker_id -> OrgWorker)
    """
    workers = [
        OrgWorker(
            id="ceo",
            name="CEO",
            boss_id=None,
            is_manager=True,
            role_id="executive",
        ),
        OrgWorker(
            id="eng-director",
            name="Engineering Director",
            boss_id="ceo",
            is_manager=True,
            role_id="director",
            team_id="engineering",
        ),
        OrgWorker(
            id="prod-director",
            name="Product Director",
            boss_id="ceo",
            is_manager=True,
            role_id="director",
            team_id="product",
        ),
        OrgWorker(
            id="eng-manager-1",
            name="Engineering Manager",
            boss_id="eng-director",
            is_manager=True,
            role_id="manager",
            team_id="engineering",
        ),
        OrgWorker(
            id="dev-1",
            name="Developer 1",
            boss_id="eng-manager-1",
            is_manager=False,
            role_id="developer",
            team_id="engineering",
            skills={"coding": 80, "reasoning": 70},
            cost=50,
        ),
        OrgWorker(
            id="dev-2",
            name="Developer 2",
            boss_id="eng-manager-1",
            is_manager=False,
            role_id="developer",
            team_id="engineering",
            skills={"coding": 75, "reasoning": 65},
            cost=45,
        ),
    ]

    loader = InMemoryOrgLoader()
    loader.add_workers(workers)

    topology = loader.load_topology()
    worker_dict = {w.id: w for w in workers}

    return topology, worker_dict

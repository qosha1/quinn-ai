"""
Hierarchical escalation routing based on org-chart hierarchy.

This module provides routing logic for escalating issues through the
organizational hierarchy. It determines the path from a worker up through
their management chain and attempts resolution at each level.

The actual communication (API calls, messages) is handled by EscalationInterface
implementations passed to the router - this module only handles routing logic.
"""

from dataclasses import dataclass

from ..core.task import Task
from .interface import EscalationInterface, EscalationResponse


@dataclass
class WorkerNode:
    """
    A node in the organizational hierarchy.

    Represents a worker's position in the org chart, including their
    reporting relationship and management status.

    Attributes:
        id: Unique identifier for this worker.
        name: Display name of the worker.
        boss_id: ID of the worker's direct supervisor, or None if they
            report directly to the board (e.g., CEO).
        is_manager: Whether this worker has direct reports.
    """

    id: str
    name: str
    boss_id: str | None
    is_manager: bool


class OrgTopology:
    """
    Simple representation of organizational hierarchy.

    Stores worker nodes and provides traversal methods for navigating
    the org chart in both directions (up to bosses, down to subordinates).

    Attributes:
        nodes: Dictionary mapping worker IDs to their WorkerNode objects.
    """

    def __init__(self) -> None:
        """Initialize an empty org topology."""
        self.nodes: dict[str, WorkerNode] = {}

    def add_node(self, node: WorkerNode) -> None:
        """
        Add a worker node to the topology.

        Args:
            node: The WorkerNode to add.
        """
        self.nodes[node.id] = node

    def get_boss(self, worker_id: str) -> str | None:
        """
        Get the direct supervisor of a worker.

        Args:
            worker_id: ID of the worker to find the boss for.

        Returns:
            ID of the worker's direct supervisor, or None if the worker
            reports to the board or doesn't exist in the topology.
        """
        node = self.nodes.get(worker_id)
        if node is None:
            return None
        return node.boss_id

    def get_subordinates(self, worker_id: str) -> list[str]:
        """
        Get all direct reports of a worker.

        Args:
            worker_id: ID of the worker to find subordinates for.

        Returns:
            List of worker IDs who report directly to this worker.
            Empty list if the worker has no direct reports or doesn't
            exist in the topology.
        """
        return [
            node.id for node in self.nodes.values() if node.boss_id == worker_id
        ]


class HierarchicalRouter:
    """
    Routes escalations through the organizational hierarchy.

    Given a worker and an issue, determines the escalation path up the
    management chain and attempts resolution at each level using the
    provided escalation interfaces.

    The router only handles routing logic - actual communication with
    supervisors is delegated to EscalationInterface implementations.
    """

    def __init__(self, topology: OrgTopology) -> None:
        """
        Initialize the router with an org topology.

        Args:
            topology: The organizational hierarchy to use for routing.
        """
        self.topology = topology

    def get_escalation_path(self, worker_id: str) -> list[str]:
        """
        Get the ordered escalation path for a worker.

        Traverses up the org chart from the worker's immediate boss
        to the top of the hierarchy, ending with "board" as the final
        escalation point.

        Args:
            worker_id: ID of the worker needing to escalate.

        Returns:
            Ordered list of escalation targets:
            [immediate_boss, their_boss, ..., "board"]
            Returns ["board"] if the worker has no boss or doesn't exist.
        """
        path: list[str] = []
        current_id = worker_id

        while True:
            boss_id = self.topology.get_boss(current_id)
            if boss_id is None:
                break
            path.append(boss_id)
            current_id = boss_id

        # Board is always the final escalation point
        path.append("board")
        return path

    def route(
        self,
        worker_id: str,
        issue: str,
        escalators: dict[str, EscalationInterface],
    ) -> EscalationResponse:
        """
        Route an escalation through the hierarchy until resolved.

        Attempts to resolve the issue by trying each escalation target
        in order (immediate boss first, then their boss, etc.) until
        one successfully handles it or all options are exhausted.

        Args:
            worker_id: ID of the worker escalating the issue.
            issue: Description of the problem to be resolved.
            escalators: Dictionary mapping worker/target IDs to their
                EscalationInterface implementations. Must include entries
                for each potential escalation target in the path.

        Returns:
            EscalationResponse from the first handler that resolves the
            issue, or an unresolved response if no handler could help.
        """
        path = self.get_escalation_path(worker_id)
        context = {"worker_id": worker_id, "escalation_path": path}

        for target_id in path:
            escalator = escalators.get(target_id)
            if escalator is None:
                continue

            if not escalator.can_handle(issue):
                continue

            response = escalator.ask(issue, context)
            if response.resolved:
                return response

        # No one could resolve the issue
        return EscalationResponse(
            resolved=False,
            guidance="",
            new_tasks=[],
            escalated_to=None,
        )


def create_simple_topology(workers: list[dict]) -> OrgTopology:
    """
    Create an OrgTopology from a list of worker dictionaries.

    Factory function for building topologies from simple data structures,
    useful for configuration-driven org chart creation.

    Args:
        workers: List of dictionaries with keys:
            - "id": Unique worker identifier (required)
            - "name": Display name (required)
            - "boss_id": ID of direct supervisor, or None (optional, defaults to None)

    Returns:
        OrgTopology populated with WorkerNode objects for each worker.
        The is_manager field is automatically computed based on whether
        other workers report to each worker.

    Example:
        >>> workers = [
        ...     {"id": "ceo", "name": "Alice", "boss_id": None},
        ...     {"id": "eng_lead", "name": "Bob", "boss_id": "ceo"},
        ...     {"id": "dev1", "name": "Carol", "boss_id": "eng_lead"},
        ... ]
        >>> topology = create_simple_topology(workers)
        >>> topology.get_boss("dev1")
        'eng_lead'
    """
    topology = OrgTopology()

    # First pass: determine who has subordinates
    subordinate_counts: dict[str, int] = {}
    for worker in workers:
        boss_id = worker.get("boss_id")
        if boss_id is not None:
            subordinate_counts[boss_id] = subordinate_counts.get(boss_id, 0) + 1

    # Second pass: create nodes with is_manager computed
    for worker in workers:
        worker_id = worker["id"]
        node = WorkerNode(
            id=worker_id,
            name=worker["name"],
            boss_id=worker.get("boss_id"),
            is_manager=subordinate_counts.get(worker_id, 0) > 0,
        )
        topology.add_node(node)

    return topology

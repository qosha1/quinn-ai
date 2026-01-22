"""Tests for the escalation system.

Tests cover:
- EscalationResponse dataclass
- MockEscalation and NoopEscalation implementations
- HierarchicalRouter and OrgTopology for path determination
- OrgEscalation, BoardNotifier, BoardEscalation for org-chart escalation
- InMemoryOrgEscalation and InMemoryBoardEscalation for testing
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from shared.escalation.interface import (
    EscalationResponse,
    MockEscalation,
    NoopEscalation,
)
from shared.escalation.hierarchical import (
    HierarchicalRouter,
    OrgTopology,
    WorkerNode,
    create_simple_topology,
)
from shared.org.escalation import (
    BoardEscalation,
    BoardNotifier,
    InMemoryBoardEscalation,
    InMemoryOrgEscalation,
    OrgEscalation,
)


# ============================================================================
# EscalationResponse Tests
# ============================================================================


class TestEscalationResponse:
    """Tests for EscalationResponse dataclass."""

    def test_create_resolved_response(self) -> None:
        """Can create a resolved response with guidance."""
        response = EscalationResponse(
            resolved=True,
            guidance="Follow these instructions",
            escalated_to="manager-001",
        )
        assert response.resolved is True
        assert response.guidance == "Follow these instructions"
        assert response.escalated_to == "manager-001"
        assert response.new_tasks == []

    def test_create_unresolved_response(self) -> None:
        """Can create an unresolved response."""
        response = EscalationResponse(resolved=False)
        assert response.resolved is False
        assert response.guidance == ""
        assert response.escalated_to is None
        assert response.new_tasks == []

    def test_response_with_new_tasks(self) -> None:
        """Response can include new tasks."""
        from shared.wrkr.core.task import Task

        task = Task(id="new-task", title="New Task", description="Do this")
        response = EscalationResponse(
            resolved=True,
            guidance="Here's a new task",
            new_tasks=[task],
            escalated_to="manager",
        )
        assert len(response.new_tasks) == 1
        assert response.new_tasks[0].id == "new-task"


# ============================================================================
# MockEscalation Tests
# ============================================================================


class TestMockEscalation:
    """Tests for MockEscalation helper class."""

    def test_default_resolves_issues(self) -> None:
        """MockEscalation resolves issues by default."""
        mock = MockEscalation()
        response = mock.ask("Need help", {"task_id": "123"})

        assert response.resolved is True
        assert response.guidance == "Mock guidance provided."
        assert response.escalated_to == "mock_handler"

    def test_configurable_resolve_behavior(self) -> None:
        """Can configure MockEscalation to not resolve."""
        mock = MockEscalation(resolve_issues=False)
        response = mock.ask("Need help", {})

        assert response.resolved is False
        assert response.guidance == ""
        assert response.escalated_to is None

    def test_configurable_guidance(self) -> None:
        """Can configure custom guidance message."""
        mock = MockEscalation(
            resolve_issues=True,
            default_guidance="Custom guidance here",
        )
        response = mock.ask("Issue", {})

        assert response.guidance == "Custom guidance here"

    def test_configurable_escalated_to_name(self) -> None:
        """Can configure custom escalated_to name."""
        mock = MockEscalation(
            resolve_issues=True,
            escalated_to_name="custom_handler",
        )
        response = mock.ask("Issue", {})

        assert response.escalated_to == "custom_handler"

    def test_tracks_ask_calls(self) -> None:
        """MockEscalation records all ask() calls."""
        mock = MockEscalation()

        mock.ask("First issue", {"ctx": 1})
        mock.ask("Second issue", {"ctx": 2})

        assert len(mock.asks) == 2
        assert mock.asks[0] == ("First issue", {"ctx": 1})
        assert mock.asks[1] == ("Second issue", {"ctx": 2})

    def test_tracks_report_calls(self) -> None:
        """MockEscalation records all report() calls."""
        mock = MockEscalation()

        mock.report("Progress update", {"percent": 50})
        mock.report("Done", None)

        assert len(mock.reports) == 2
        assert mock.reports[0] == ("Progress update", {"percent": 50})
        assert mock.reports[1] == ("Done", None)

    def test_tracks_can_handle_calls(self) -> None:
        """MockEscalation records all can_handle() calls."""
        mock = MockEscalation()

        mock.can_handle("Issue 1")
        mock.can_handle("Issue 2")

        assert len(mock.can_handle_checks) == 2
        assert "Issue 1" in mock.can_handle_checks
        assert "Issue 2" in mock.can_handle_checks

    def test_can_handle_returns_resolve_issues(self) -> None:
        """can_handle() returns the resolve_issues setting."""
        mock_resolves = MockEscalation(resolve_issues=True)
        mock_unresolved = MockEscalation(resolve_issues=False)

        assert mock_resolves.can_handle("Issue") is True
        assert mock_unresolved.can_handle("Issue") is False

    def test_reset_clears_tracking(self) -> None:
        """reset() clears all tracked interactions."""
        mock = MockEscalation()
        mock.ask("Issue", {})
        mock.report("Update", None)
        mock.can_handle("Check")

        mock.reset()

        assert len(mock.asks) == 0
        assert len(mock.reports) == 0
        assert len(mock.can_handle_checks) == 0


# ============================================================================
# NoopEscalation Tests
# ============================================================================


class TestNoopEscalation:
    """Tests for NoopEscalation (disabled escalation)."""

    def test_ask_returns_unresolved(self) -> None:
        """NoopEscalation always returns unresolved."""
        noop = NoopEscalation()
        response = noop.ask("Any issue", {"any": "context"})

        assert response.resolved is False
        assert response.guidance == ""
        assert response.escalated_to is None
        assert response.new_tasks == []

    def test_report_does_nothing(self) -> None:
        """report() silently does nothing."""
        noop = NoopEscalation()
        # Should not raise
        noop.report("Update", {"data": "value"})

    def test_can_handle_always_false(self) -> None:
        """can_handle() always returns False."""
        noop = NoopEscalation()
        assert noop.can_handle("Any issue") is False


# ============================================================================
# OrgTopology Tests
# ============================================================================


class TestOrgTopology:
    """Tests for OrgTopology hierarchy representation."""

    def test_add_and_retrieve_node(self) -> None:
        """Can add nodes and retrieve them."""
        topology = OrgTopology()
        node = WorkerNode(id="w1", name="Worker 1", boss_id="mgr1", is_manager=False)
        topology.add_node(node)

        assert "w1" in topology.nodes
        assert topology.nodes["w1"].name == "Worker 1"

    def test_get_boss(self) -> None:
        """get_boss() returns the worker's supervisor."""
        topology = OrgTopology()
        topology.add_node(
            WorkerNode(id="ceo", name="CEO", boss_id=None, is_manager=True)
        )
        topology.add_node(
            WorkerNode(id="mgr", name="Manager", boss_id="ceo", is_manager=True)
        )
        topology.add_node(
            WorkerNode(id="dev", name="Developer", boss_id="mgr", is_manager=False)
        )

        assert topology.get_boss("dev") == "mgr"
        assert topology.get_boss("mgr") == "ceo"
        assert topology.get_boss("ceo") is None

    def test_get_boss_unknown_worker(self) -> None:
        """get_boss() returns None for unknown workers."""
        topology = OrgTopology()
        assert topology.get_boss("unknown") is None

    def test_get_subordinates(self) -> None:
        """get_subordinates() returns direct reports."""
        topology = OrgTopology()
        topology.add_node(
            WorkerNode(id="mgr", name="Manager", boss_id=None, is_manager=True)
        )
        topology.add_node(
            WorkerNode(id="dev1", name="Dev 1", boss_id="mgr", is_manager=False)
        )
        topology.add_node(
            WorkerNode(id="dev2", name="Dev 2", boss_id="mgr", is_manager=False)
        )

        subs = topology.get_subordinates("mgr")
        assert len(subs) == 2
        assert "dev1" in subs
        assert "dev2" in subs

    def test_get_subordinates_empty(self) -> None:
        """get_subordinates() returns empty list for leaf workers."""
        topology = OrgTopology()
        topology.add_node(
            WorkerNode(id="dev", name="Developer", boss_id="mgr", is_manager=False)
        )

        assert topology.get_subordinates("dev") == []


class TestCreateSimpleTopology:
    """Tests for create_simple_topology helper."""

    def test_creates_topology_from_dicts(self) -> None:
        """Creates topology from list of worker dicts."""
        workers = [
            {"id": "ceo", "name": "Alice", "boss_id": None},
            {"id": "mgr", "name": "Bob", "boss_id": "ceo"},
            {"id": "dev", "name": "Carol", "boss_id": "mgr"},
        ]

        topology = create_simple_topology(workers)

        assert len(topology.nodes) == 3
        assert topology.get_boss("dev") == "mgr"
        assert topology.get_boss("mgr") == "ceo"
        assert topology.get_boss("ceo") is None

    def test_computes_is_manager(self) -> None:
        """Automatically computes is_manager based on subordinates."""
        workers = [
            {"id": "ceo", "name": "Alice", "boss_id": None},
            {"id": "mgr", "name": "Bob", "boss_id": "ceo"},
            {"id": "dev", "name": "Carol", "boss_id": "mgr"},
        ]

        topology = create_simple_topology(workers)

        assert topology.nodes["ceo"].is_manager is True  # Has subordinates
        assert topology.nodes["mgr"].is_manager is True  # Has subordinates
        assert topology.nodes["dev"].is_manager is False  # No subordinates


# ============================================================================
# HierarchicalRouter Tests
# ============================================================================


class TestHierarchicalRouter:
    """Tests for HierarchicalRouter escalation path determination."""

    @pytest.fixture
    def simple_topology(self) -> OrgTopology:
        """Create a simple 3-level hierarchy for testing."""
        return create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "mgr", "name": "Manager", "boss_id": "ceo"},
            {"id": "dev", "name": "Developer", "boss_id": "mgr"},
        ])

    def test_get_escalation_path_leaf_worker(self, simple_topology: OrgTopology) -> None:
        """Escalation path goes up the hierarchy to board."""
        router = HierarchicalRouter(simple_topology)
        path = router.get_escalation_path("dev")

        assert path == ["mgr", "ceo", "board"]

    def test_get_escalation_path_manager(self, simple_topology: OrgTopology) -> None:
        """Manager's path goes to their boss and board."""
        router = HierarchicalRouter(simple_topology)
        path = router.get_escalation_path("mgr")

        assert path == ["ceo", "board"]

    def test_get_escalation_path_ceo(self, simple_topology: OrgTopology) -> None:
        """CEO's path goes directly to board."""
        router = HierarchicalRouter(simple_topology)
        path = router.get_escalation_path("ceo")

        assert path == ["board"]

    def test_get_escalation_path_unknown_worker(self, simple_topology: OrgTopology) -> None:
        """Unknown worker gets path directly to board."""
        router = HierarchicalRouter(simple_topology)
        path = router.get_escalation_path("unknown")

        assert path == ["board"]

    def test_route_resolves_at_first_handler(self, simple_topology: OrgTopology) -> None:
        """Route stops at first handler that resolves the issue."""
        router = HierarchicalRouter(simple_topology)

        mgr_handler = MockEscalation(resolve_issues=True)
        ceo_handler = MockEscalation(resolve_issues=True)

        escalators = {
            "mgr": mgr_handler,
            "ceo": ceo_handler,
        }

        response = router.route("dev", "Need help", escalators)

        assert response.resolved is True
        assert len(mgr_handler.asks) == 1  # Manager was asked
        assert len(ceo_handler.asks) == 0  # CEO was not asked (manager resolved it)

    def test_route_continues_when_unresolved(self, simple_topology: OrgTopology) -> None:
        """Route continues to next handler when first doesn't resolve."""
        router = HierarchicalRouter(simple_topology)

        # Custom handler that can_handle returns True but ask returns unresolved
        class UnresolvedHandler:
            def __init__(self) -> None:
                self.asks: list[tuple[str, dict]] = []

            def can_handle(self, issue: str) -> bool:
                return True  # Says it can handle

            def ask(self, issue: str, context: dict) -> EscalationResponse:
                self.asks.append((issue, context))
                return EscalationResponse(resolved=False)  # But doesn't resolve

        mgr_handler = UnresolvedHandler()
        ceo_handler = MockEscalation(resolve_issues=True)

        escalators = {
            "mgr": mgr_handler,
            "ceo": ceo_handler,
        }

        response = router.route("dev", "Need help", escalators)

        assert response.resolved is True
        assert len(mgr_handler.asks) == 1  # Manager was asked first
        assert len(ceo_handler.asks) == 1  # CEO was asked after

    def test_route_skips_handlers_that_cannot_handle(
        self, simple_topology: OrgTopology
    ) -> None:
        """Route skips handlers where can_handle() returns False."""
        router = HierarchicalRouter(simple_topology)

        # Manager can't handle but would resolve if asked
        mgr_handler = MockEscalation(resolve_issues=False)
        ceo_handler = MockEscalation(resolve_issues=True)

        escalators = {
            "mgr": mgr_handler,
            "ceo": ceo_handler,
        }

        response = router.route("dev", "Need help", escalators)

        # Manager can_handle returns False, so skipped; then returns False on ask too
        # CEO gets asked and resolves
        assert response.resolved is True

    def test_route_returns_unresolved_when_no_handler(
        self, simple_topology: OrgTopology
    ) -> None:
        """Route returns unresolved when no handler exists or all fail."""
        router = HierarchicalRouter(simple_topology)

        # No handlers provided
        response = router.route("dev", "Need help", {})

        assert response.resolved is False
        assert response.escalated_to is None

    def test_route_passes_context_to_handlers(self, simple_topology: OrgTopology) -> None:
        """Route passes worker_id and escalation_path in context."""
        router = HierarchicalRouter(simple_topology)
        mgr_handler = MockEscalation(resolve_issues=True)

        response = router.route("dev", "Need help", {"mgr": mgr_handler})

        issue, context = mgr_handler.asks[0]
        assert context["worker_id"] == "dev"
        assert context["escalation_path"] == ["mgr", "ceo", "board"]


# ============================================================================
# BoardNotifier Tests
# ============================================================================


class TestBoardNotifier:
    """Tests for BoardNotifier (human oversight notification)."""

    def test_notify_stores_notification(self) -> None:
        """notify() stores the notification for retrieval."""
        notifier = BoardNotifier()
        notifier.notify("Urgent issue", {"task_id": "123"})

        notifications = notifier.get_pending_notifications()
        assert len(notifications) == 1
        assert notifications[0]["issue"] == "Urgent issue"
        assert notifications[0]["context"]["task_id"] == "123"

    def test_notify_calls_callback(self) -> None:
        """notify() calls the callback if provided."""
        callback = MagicMock()
        notifier = BoardNotifier(notification_callback=callback)

        notifier.notify("Issue", {"ctx": "data"})

        callback.assert_called_once_with("Issue", {"ctx": "data"})

    def test_clear_notifications(self) -> None:
        """clear_notifications() removes all pending notifications."""
        notifier = BoardNotifier()
        notifier.notify("Issue 1", {})
        notifier.notify("Issue 2", {})

        notifier.clear_notifications()

        assert len(notifier.get_pending_notifications()) == 0

    def test_max_notifications_limit(self) -> None:
        """Notifications are limited to max_notifications."""
        notifier = BoardNotifier(max_notifications=3)

        for i in range(5):
            notifier.notify(f"Issue {i}", {})

        notifications = notifier.get_pending_notifications()
        assert len(notifications) == 3
        # Oldest are discarded, newest are kept
        assert notifications[0]["issue"] == "Issue 2"
        assert notifications[2]["issue"] == "Issue 4"


# ============================================================================
# BoardEscalation Tests
# ============================================================================


class TestBoardEscalation:
    """Tests for BoardEscalation (EscalationInterface for board)."""

    def test_ask_notifies_board(self) -> None:
        """ask() notifies the board and returns resolved."""
        notifier = BoardNotifier()
        board_esc = BoardEscalation(notifier)

        response = board_esc.ask("Need human help", {"worker_id": "dev1"})

        assert response.resolved is True
        assert response.escalated_to == "board"
        assert "board" in response.guidance.lower()
        assert len(notifier.get_pending_notifications()) == 1

    def test_can_handle_always_true(self) -> None:
        """Board can always handle escalations."""
        notifier = BoardNotifier()
        board_esc = BoardEscalation(notifier)

        assert board_esc.can_handle("Any issue") is True

    def test_report_is_noop(self) -> None:
        """report() does nothing for board."""
        notifier = BoardNotifier()
        board_esc = BoardEscalation(notifier)

        # Should not raise
        board_esc.report("Status update", {"data": "value"})


# ============================================================================
# InMemoryOrgEscalation Tests
# ============================================================================


class TestInMemoryOrgEscalation:
    """Tests for InMemoryOrgEscalation (testing helper)."""

    @pytest.fixture
    def simple_topology(self) -> OrgTopology:
        """Create a simple hierarchy."""
        return create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "mgr", "name": "Manager", "boss_id": "ceo"},
            {"id": "dev", "name": "Developer", "boss_id": "mgr"},
        ])

    def test_ask_routes_through_hierarchy(self, simple_topology: OrgTopology) -> None:
        """ask() routes through hierarchy to board."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=simple_topology,
        )

        response = escalation.ask("Need help", {"task_id": "123"})

        # Board always resolves
        assert response.resolved is True
        assert response.escalated_to == "board"

    def test_ask_records_escalation(self, simple_topology: OrgTopology) -> None:
        """ask() records the escalation."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=simple_topology,
        )

        escalation.ask("Issue 1", {"ctx": 1})
        escalation.ask("Issue 2", {"ctx": 2})

        assert len(escalation.escalations) == 2
        assert escalation.escalations[0]["issue"] == "Issue 1"
        assert escalation.escalations[1]["issue"] == "Issue 2"

    def test_ask_with_custom_handlers(self, simple_topology: OrgTopology) -> None:
        """ask() uses custom handlers when provided."""
        mgr_handler = MockEscalation(resolve_issues=True)

        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=simple_topology,
            worker_handlers={"mgr": mgr_handler},
        )

        response = escalation.ask("Help me", {})

        assert response.resolved is True
        assert len(mgr_handler.asks) == 1

    def test_report_records_report(self, simple_topology: OrgTopology) -> None:
        """report() records the report."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=simple_topology,
        )

        escalation.report("Progress update", {"percent": 50})

        assert len(escalation.reports) == 1
        assert escalation.reports[0]["summary"] == "Progress update"
        assert escalation.reports[0]["metadata"]["percent"] == 50

    def test_can_handle_with_board_always_true(
        self, simple_topology: OrgTopology
    ) -> None:
        """can_handle() returns True when board is in path."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=simple_topology,
        )

        assert escalation.can_handle("Any issue") is True

    def test_board_notifications_recorded(self, simple_topology: OrgTopology) -> None:
        """Board notifications are recorded when escalation reaches board."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=simple_topology,
        )

        escalation.ask("Urgent", {"important": True})

        assert len(escalation.board_notifications) == 1
        assert escalation.board_notifications[0]["issue"] == "Urgent"


# ============================================================================
# InMemoryBoardEscalation Tests
# ============================================================================


class TestInMemoryBoardEscalation:
    """Tests for InMemoryBoardEscalation."""

    def test_ask_stores_notification(self) -> None:
        """ask() stores the notification and returns resolved."""
        notifications: list[dict[str, Any]] = []
        board = InMemoryBoardEscalation(notifications)

        response = board.ask("Issue", {"context": "data"})

        assert response.resolved is True
        assert response.escalated_to == "board"
        assert len(notifications) == 1
        assert notifications[0]["issue"] == "Issue"

    def test_can_handle_always_true(self) -> None:
        """Board can always handle."""
        board = InMemoryBoardEscalation([])
        assert board.can_handle("Anything") is True

    def test_report_is_noop(self) -> None:
        """report() does nothing."""
        board = InMemoryBoardEscalation([])
        board.report("Update", {})  # Should not raise


# ============================================================================
# Integration Tests
# ============================================================================


class TestEscalationIntegration:
    """Integration tests for the full escalation flow."""

    def test_full_escalation_chain(self) -> None:
        """Test escalation from developer through manager to board."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "mgr", "name": "Manager", "boss_id": "ceo"},
            {"id": "dev", "name": "Developer", "boss_id": "mgr"},
        ])

        # Custom handler that claims to handle but returns unresolved
        class UnresolvedHandler:
            def __init__(self) -> None:
                self.asks: list[tuple[str, dict]] = []

            def can_handle(self, issue: str) -> bool:
                return True  # Says it can handle

            def ask(self, issue: str, context: dict) -> EscalationResponse:
                self.asks.append((issue, context))
                return EscalationResponse(resolved=False)  # But doesn't resolve

            def report(self, summary: str, metadata: dict[str, Any] | None = None) -> None:
                pass

        mgr_handler = UnresolvedHandler()
        ceo_handler = UnresolvedHandler()

        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=topology,
            worker_handlers={
                "mgr": mgr_handler,
                "ceo": ceo_handler,
            },
        )

        response = escalation.ask("Complex issue", {"needs": "human"})

        # All handlers were consulted
        assert len(mgr_handler.asks) == 1
        assert len(ceo_handler.asks) == 1

        # Board ultimately resolved
        assert response.resolved is True
        assert response.escalated_to == "board"
        assert len(escalation.board_notifications) == 1

    def test_escalation_stops_at_first_resolver(self) -> None:
        """Escalation stops as soon as someone resolves the issue."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "mgr", "name": "Manager", "boss_id": "ceo"},
            {"id": "dev", "name": "Developer", "boss_id": "mgr"},
        ])

        # Manager resolves the issue
        mgr_handler = MockEscalation(resolve_issues=True, escalated_to_name="mgr")
        ceo_handler = MockEscalation(resolve_issues=True)

        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=topology,
            worker_handlers={
                "mgr": mgr_handler,
                "ceo": ceo_handler,
            },
        )

        response = escalation.ask("Simple issue", {})

        # Only manager was consulted
        assert len(mgr_handler.asks) == 1
        assert len(ceo_handler.asks) == 0

        # Manager resolved
        assert response.resolved is True
        assert response.escalated_to == "mgr"

        # No board notification (didn't reach board)
        assert len(escalation.board_notifications) == 0

    def test_deep_hierarchy_escalation(self) -> None:
        """Test escalation through a deep hierarchy."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "vp", "name": "VP", "boss_id": "ceo"},
            {"id": "director", "name": "Director", "boss_id": "vp"},
            {"id": "mgr", "name": "Manager", "boss_id": "director"},
            {"id": "senior", "name": "Senior Dev", "boss_id": "mgr"},
            {"id": "junior", "name": "Junior Dev", "boss_id": "senior"},
        ])

        router = HierarchicalRouter(topology)
        path = router.get_escalation_path("junior")

        assert path == ["senior", "mgr", "director", "vp", "ceo", "board"]


# ============================================================================
# EscalationManager Tests
# ============================================================================


from shared.escalation.manager import (
    EscalationConfig,
    EscalationEntry,
    EscalationHistoryEntry,
    EscalationManager,
    EscalationState,
    InMemoryNotificationHandler,
)


class TestEscalationConfig:
    """Tests for EscalationConfig defaults and customization."""

    def test_default_values(self) -> None:
        """Config has sensible defaults."""
        config = EscalationConfig()

        assert config.timeout_seconds == 300
        assert config.max_escalation_depth == 10
        assert config.auto_escalate_on_timeout is True
        assert config.retry_attempts == 1
        assert config.enable_history is True
        assert config.max_history_size == 10000
        assert config.max_queue_size == 1000

    def test_custom_values(self) -> None:
        """Can customize config values."""
        config = EscalationConfig(
            timeout_seconds=60,
            max_escalation_depth=5,
            auto_escalate_on_timeout=False,
            retry_attempts=3,
            enable_history=False,
            max_history_size=100,
            max_queue_size=50,
        )

        assert config.timeout_seconds == 60
        assert config.max_escalation_depth == 5
        assert config.auto_escalate_on_timeout is False
        assert config.retry_attempts == 3
        assert config.enable_history is False
        assert config.max_history_size == 100
        assert config.max_queue_size == 50


class TestEscalationManager:
    """Tests for EscalationManager coordination."""

    @pytest.fixture
    def simple_topology(self) -> OrgTopology:
        """Create a simple hierarchy."""
        return create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "mgr", "name": "Manager", "boss_id": "ceo"},
            {"id": "dev", "name": "Developer", "boss_id": "mgr"},
        ])

    @pytest.fixture
    def manager(self, simple_topology: OrgTopology) -> EscalationManager:
        """Create a manager with default config."""
        return EscalationManager(simple_topology)

    def test_submit_creates_entry(self, manager: EscalationManager) -> None:
        """submit() creates an escalation entry."""
        entry = manager.submit("dev", "Need help", {"task_id": "123"})

        assert entry.id.startswith("esc-")
        assert entry.worker_id == "dev"
        assert entry.issue == "Need help"
        assert entry.context["task_id"] == "123"
        assert entry.state == EscalationState.PENDING
        assert entry.escalation_path == ["mgr", "ceo", "board"]

    def test_submit_sets_timeout(self, manager: EscalationManager) -> None:
        """submit() sets timeout based on config."""
        entry = manager.submit("dev", "Issue")

        assert entry.timeout_at is not None
        assert entry.timeout_at > entry.created_at

    def test_submit_custom_timeout(
        self, simple_topology: OrgTopology
    ) -> None:
        """submit() allows custom timeout per escalation."""
        config = EscalationConfig(timeout_seconds=300)
        manager = EscalationManager(simple_topology, config)

        entry = manager.submit("dev", "Issue", timeout_seconds=60)

        # Should use custom timeout, not config default
        assert entry.timeout_at is not None
        delta = entry.timeout_at - entry.created_at
        assert 59 <= delta.total_seconds() <= 61

    def test_get_entry(self, manager: EscalationManager) -> None:
        """get_entry() retrieves by ID."""
        entry = manager.submit("dev", "Issue")

        retrieved = manager.get_entry(entry.id)

        assert retrieved is not None
        assert retrieved.id == entry.id

    def test_get_entry_not_found(self, manager: EscalationManager) -> None:
        """get_entry() returns None for unknown ID."""
        assert manager.get_entry("unknown-id") is None

    def test_get_pending(self, manager: EscalationManager) -> None:
        """get_pending() returns only pending escalations."""
        entry1 = manager.submit("dev", "Issue 1")
        entry2 = manager.submit("dev", "Issue 2")

        pending = manager.get_pending()

        assert len(pending) == 2
        ids = [e.id for e in pending]
        assert entry1.id in ids
        assert entry2.id in ids

    def test_get_by_worker(self, manager: EscalationManager) -> None:
        """get_by_worker() filters by worker ID."""
        manager.submit("dev", "Dev issue 1")
        manager.submit("dev", "Dev issue 2")
        manager.submit("mgr", "Mgr issue")

        dev_entries = manager.get_by_worker("dev")
        mgr_entries = manager.get_by_worker("mgr")

        assert len(dev_entries) == 2
        assert len(mgr_entries) == 1

    def test_process_resolves_escalation(
        self, manager: EscalationManager
    ) -> None:
        """process() resolves escalation through hierarchy."""
        entry = manager.submit("dev", "Need help")

        mgr_handler = MockEscalation(resolve_issues=True, escalated_to_name="mgr")
        response = manager.process(entry.id, {"mgr": mgr_handler})

        assert response.resolved is True
        assert response.escalated_to == "mgr"

        # Entry should be resolved and moved to history
        assert manager.get_entry(entry.id) is None
        assert manager.history_size == 1

    def test_process_fails_after_retries(
        self, simple_topology: OrgTopology
    ) -> None:
        """process() fails after exhausting retries."""
        config = EscalationConfig(retry_attempts=1)
        manager = EscalationManager(simple_topology, config)

        entry = manager.submit("dev", "Impossible issue")

        # No handlers - will fail
        response = manager.process(entry.id, {})

        assert response.resolved is False
        assert manager.get_entry(entry.id) is None
        history = manager.get_history()
        assert len(history) == 1
        assert history[0].state == EscalationState.FAILED

    def test_process_not_found_raises(self, manager: EscalationManager) -> None:
        """process() raises KeyError for unknown ID."""
        with pytest.raises(KeyError):
            manager.process("unknown-id", {})

    def test_process_already_resolved_raises(
        self, manager: EscalationManager
    ) -> None:
        """process() raises ValueError for already-resolved escalation."""
        entry = manager.submit("dev", "Issue")

        # Resolve it
        mgr_handler = MockEscalation(resolve_issues=True)
        manager.process(entry.id, {"mgr": mgr_handler})

        # Try to process again - should raise
        with pytest.raises(KeyError):  # Not found because it's in history
            manager.process(entry.id, {"mgr": mgr_handler})

    def test_cancel_pending(self, manager: EscalationManager) -> None:
        """cancel() removes pending escalation."""
        entry = manager.submit("dev", "Issue")

        result = manager.cancel(entry.id)

        assert result is True
        assert manager.get_entry(entry.id) is None

    def test_cancel_not_found(self, manager: EscalationManager) -> None:
        """cancel() returns False for unknown ID."""
        assert manager.cancel("unknown-id") is False

    def test_queue_size_limit(self, simple_topology: OrgTopology) -> None:
        """submit() raises when queue is full."""
        config = EscalationConfig(max_queue_size=2)
        manager = EscalationManager(simple_topology, config)

        manager.submit("dev", "Issue 1")
        manager.submit("dev", "Issue 2")

        with pytest.raises(RuntimeError, match="queue full"):
            manager.submit("dev", "Issue 3")

    def test_history_tracking(self, manager: EscalationManager) -> None:
        """History tracks completed escalations."""
        entry = manager.submit("dev", "Issue")

        mgr_handler = MockEscalation(resolve_issues=True, escalated_to_name="mgr")
        manager.process(entry.id, {"mgr": mgr_handler})

        history = manager.get_history()

        assert len(history) == 1
        assert history[0].id == entry.id
        assert history[0].worker_id == "dev"
        assert history[0].state == EscalationState.RESOLVED
        assert history[0].resolved_by == "mgr"

    def test_history_filter_by_worker(self, manager: EscalationManager) -> None:
        """get_history() filters by worker ID."""
        entry1 = manager.submit("dev", "Dev issue")
        entry2 = manager.submit("mgr", "Mgr issue")

        mgr_handler = MockEscalation(resolve_issues=True)
        manager.process(entry1.id, {"mgr": mgr_handler})
        manager.process(entry2.id, {"ceo": mgr_handler})

        dev_history = manager.get_history(worker_id="dev")
        mgr_history = manager.get_history(worker_id="mgr")

        assert len(dev_history) == 1
        assert len(mgr_history) == 1

    def test_history_filter_by_state(self, manager: EscalationManager) -> None:
        """get_history() filters by state."""
        entry1 = manager.submit("dev", "Resolvable")
        entry2 = manager.submit("dev", "Unresolvable")

        mgr_handler = MockEscalation(resolve_issues=True)
        manager.process(entry1.id, {"mgr": mgr_handler})
        manager.process(entry2.id, {})  # No handlers, will fail

        resolved = manager.get_history(state=EscalationState.RESOLVED)
        failed = manager.get_history(state=EscalationState.FAILED)

        assert len(resolved) == 1
        assert len(failed) == 1

    def test_history_disabled(self, simple_topology: OrgTopology) -> None:
        """History is not tracked when disabled."""
        config = EscalationConfig(enable_history=False)
        manager = EscalationManager(simple_topology, config)

        entry = manager.submit("dev", "Issue")
        mgr_handler = MockEscalation(resolve_issues=True)
        manager.process(entry.id, {"mgr": mgr_handler})

        assert manager.history_size == 0


class TestInMemoryNotificationHandler:
    """Tests for InMemoryNotificationHandler."""

    def test_stores_notifications(self) -> None:
        """Handler stores notifications."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "dev", "name": "Dev", "boss_id": "ceo"},
        ])
        handler = InMemoryNotificationHandler()
        manager = EscalationManager(topology, notification_handler=handler)

        entry = manager.submit("dev", "Issue")

        assert len(handler.notifications) == 1
        assert handler.notifications[0][1] == "created"

    def test_tracks_events(self) -> None:
        """Handler tracks multiple events for same escalation."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "dev", "name": "Dev", "boss_id": "ceo"},
        ])
        handler = InMemoryNotificationHandler()
        manager = EscalationManager(topology, notification_handler=handler)

        entry = manager.submit("dev", "Issue")
        mgr_handler = MockEscalation(resolve_issues=True)
        manager.process(entry.id, {"ceo": mgr_handler})

        events = handler.get_events(entry.id)

        assert "created" in events
        assert "resolved" in events

    def test_clear_notifications(self) -> None:
        """clear() removes all notifications."""
        handler = InMemoryNotificationHandler()
        entry = EscalationEntry(
            id="test", worker_id="dev", issue="Test", context={}
        )
        handler.notify(entry, "test")

        handler.clear()

        assert len(handler.notifications) == 0


class TestEscalationManagerContextManager:
    """Tests for EscalationManager context manager support."""

    def test_context_manager_starts_and_stops(self) -> None:
        """Context manager starts/stops the manager."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
        ])

        with EscalationManager(topology) as manager:
            assert manager._running is True

        assert manager._running is False

    def test_manual_start_stop(self) -> None:
        """Can manually start and stop."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
        ])
        manager = EscalationManager(topology)

        manager.start()
        assert manager._running is True

        manager.stop()
        assert manager._running is False

    def test_double_start_is_safe(self) -> None:
        """Calling start() twice doesn't cause issues."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
        ])
        manager = EscalationManager(topology)

        manager.start()
        manager.start()  # Should be no-op
        assert manager._running is True

        manager.stop()

    def test_double_stop_is_safe(self) -> None:
        """Calling stop() twice doesn't cause issues."""
        topology = create_simple_topology([
            {"id": "ceo", "name": "CEO", "boss_id": None},
        ])
        manager = EscalationManager(topology)

        manager.start()
        manager.stop()
        manager.stop()  # Should be no-op
        assert manager._running is False

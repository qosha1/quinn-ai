"""Tests for wrkr org-chart integration."""

import pytest
from datetime import datetime

from shared.org import (
    BeadsOrgLoader,
    BoardEscalation,
    BoardNotifier,
    InMemoryBoardEscalation,
    InMemoryOrgEscalation,
    InMemoryOrgLoader,
    OrgEscalation,
    OrgWorker,
    build_standard_topology,
)
from shared.escalation.interface import (
    EscalationInterface,
    EscalationResponse,
    MockEscalation,
)
from shared.escalation.hierarchical import (
    HierarchicalRouter,
    OrgTopology,
    WorkerNode,
    create_simple_topology,
)


# ============================================================================
# OrgWorker Tests
# ============================================================================


class TestOrgWorker:
    """Tests for OrgWorker dataclass."""

    def test_create_basic_worker(self) -> None:
        """Test creating a basic worker with required fields."""
        worker = OrgWorker(id="w1", name="Alice")

        assert worker.id == "w1"
        assert worker.name == "Alice"
        assert worker.boss_id is None
        assert worker.is_manager is False
        assert worker.role_id == ""
        assert worker.team_id is None
        assert worker.skills is None
        assert worker.cost == 50

    def test_create_full_worker(self) -> None:
        """Test creating a worker with all fields."""
        worker = OrgWorker(
            id="w2",
            name="Bob",
            boss_id="w1",
            is_manager=True,
            role_id="manager",
            team_id="engineering",
            skills={"coding": 80, "leadership": 70},
            cost=75,
        )

        assert worker.id == "w2"
        assert worker.boss_id == "w1"
        assert worker.is_manager is True
        assert worker.role_id == "manager"
        assert worker.team_id == "engineering"
        assert worker.skills == {"coding": 80, "leadership": 70}
        assert worker.cost == 75


# ============================================================================
# InMemoryOrgLoader Tests
# ============================================================================


class TestInMemoryOrgLoader:
    """Tests for InMemoryOrgLoader."""

    @pytest.fixture
    def loader(self) -> InMemoryOrgLoader:
        """Create an empty org loader."""
        return InMemoryOrgLoader()

    @pytest.fixture
    def workers(self) -> list[OrgWorker]:
        """Create sample workers."""
        return [
            OrgWorker(id="ceo", name="CEO", boss_id=None, is_manager=True),
            OrgWorker(id="mgr", name="Manager", boss_id="ceo", is_manager=True),
            OrgWorker(id="dev", name="Developer", boss_id="mgr", is_manager=False),
        ]

    def test_add_worker(self, loader: InMemoryOrgLoader) -> None:
        """Test adding a single worker."""
        worker = OrgWorker(id="w1", name="Test")
        loader.add_worker(worker)

        result = loader.get_worker("w1")
        assert result is not None
        assert result.id == "w1"

    def test_add_workers(
        self, loader: InMemoryOrgLoader, workers: list[OrgWorker]
    ) -> None:
        """Test adding multiple workers."""
        loader.add_workers(workers)

        assert len(loader.load_workers()) == 3

    def test_load_workers(
        self, loader: InMemoryOrgLoader, workers: list[OrgWorker]
    ) -> None:
        """Test loading all workers."""
        loader.add_workers(workers)

        result = loader.load_workers()
        assert len(result) == 3
        ids = {w.id for w in result}
        assert ids == {"ceo", "mgr", "dev"}

    def test_load_topology(
        self, loader: InMemoryOrgLoader, workers: list[OrgWorker]
    ) -> None:
        """Test loading org topology."""
        loader.add_workers(workers)

        topology = loader.load_topology()

        assert topology.get_boss("dev") == "mgr"
        assert topology.get_boss("mgr") == "ceo"
        assert topology.get_boss("ceo") is None

    def test_get_worker_not_found(self, loader: InMemoryOrgLoader) -> None:
        """Test getting a non-existent worker."""
        result = loader.get_worker("nonexistent")
        assert result is None

    def test_get_team_members(
        self, loader: InMemoryOrgLoader, workers: list[OrgWorker]
    ) -> None:
        """Test getting team members."""
        # Add team_id to workers
        workers[1].team_id = "eng"
        workers[2].team_id = "eng"
        loader.add_workers(workers)

        result = loader.get_team_members("eng")
        assert len(result) == 2
        ids = {w.id for w in result}
        assert ids == {"mgr", "dev"}

    def test_get_team_members_empty(self, loader: InMemoryOrgLoader) -> None:
        """Test getting members of non-existent team."""
        result = loader.get_team_members("nonexistent")
        assert result == []


# ============================================================================
# build_standard_topology Tests
# ============================================================================


class TestBuildStandardTopology:
    """Tests for build_standard_topology helper."""

    def test_builds_valid_topology(self) -> None:
        """Test that standard topology is valid."""
        topology, workers = build_standard_topology()

        # Check topology has expected workers
        assert "ceo" in topology.nodes
        assert "eng-director" in topology.nodes
        assert "dev-1" in topology.nodes

        # Check hierarchy
        assert topology.get_boss("dev-1") == "eng-manager-1"
        assert topology.get_boss("eng-manager-1") == "eng-director"
        assert topology.get_boss("eng-director") == "ceo"

    def test_returns_worker_dict(self) -> None:
        """Test that worker dict contains OrgWorker objects."""
        topology, workers = build_standard_topology()

        assert "ceo" in workers
        assert isinstance(workers["ceo"], OrgWorker)
        assert workers["ceo"].is_manager is True

    def test_manager_flags_correct(self) -> None:
        """Test that is_manager flags are set correctly."""
        topology, workers = build_standard_topology()

        assert workers["ceo"].is_manager is True
        assert workers["eng-director"].is_manager is True
        assert workers["dev-1"].is_manager is False
        assert workers["dev-2"].is_manager is False


# ============================================================================
# InMemoryOrgEscalation Tests
# ============================================================================


class TestInMemoryOrgEscalation:
    """Tests for InMemoryOrgEscalation."""

    @pytest.fixture
    def topology(self) -> OrgTopology:
        """Create a simple topology."""
        workers = [
            {"id": "ceo", "name": "CEO", "boss_id": None},
            {"id": "mgr", "name": "Manager", "boss_id": "ceo"},
            {"id": "dev", "name": "Developer", "boss_id": "mgr"},
        ]
        return create_simple_topology(workers)

    @pytest.fixture
    def mock_mgr_handler(self) -> MockEscalation:
        """Create a mock handler for manager."""
        return MockEscalation(
            resolve_issues=True,
            default_guidance="Manager can help.",
            escalated_to_name="mgr",
        )

    def test_escalation_path(self, topology: OrgTopology) -> None:
        """Test escalation follows org hierarchy."""
        router = HierarchicalRouter(topology)
        path = router.get_escalation_path("dev")

        assert path == ["mgr", "ceo", "board"]

    def test_escalation_resolved_by_manager(
        self,
        topology: OrgTopology,
        mock_mgr_handler: MockEscalation,
    ) -> None:
        """Test escalation resolved at manager level."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=topology,
            worker_handlers={"mgr": mock_mgr_handler},
        )

        response = escalation.ask("Need help", {"task": "test"})

        assert response.resolved is True
        assert response.escalated_to == "mgr"
        assert len(mock_mgr_handler.asks) == 1

    def test_escalation_to_board(self, topology: OrgTopology) -> None:
        """Test escalation reaches board when no handler resolves."""
        # Create handlers that don't resolve
        mgr_handler = MockEscalation(resolve_issues=False)
        ceo_handler = MockEscalation(resolve_issues=False)

        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=topology,
            worker_handlers={"mgr": mgr_handler, "ceo": ceo_handler},
        )

        response = escalation.ask("Unsolvable issue", {})

        assert response.resolved is True  # Board always resolves
        assert response.escalated_to == "board"
        assert len(escalation.board_notifications) == 1

    def test_report_recorded(self, topology: OrgTopology) -> None:
        """Test reports are recorded."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=topology,
        )

        escalation.report("Progress update", {"status": "on_track"})

        assert len(escalation.reports) == 1
        assert escalation.reports[0]["summary"] == "Progress update"
        assert escalation.reports[0]["reporter"] == "dev"

    def test_can_handle_with_handlers(
        self,
        topology: OrgTopology,
        mock_mgr_handler: MockEscalation,
    ) -> None:
        """Test can_handle returns True when handler exists."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=topology,
            worker_handlers={"mgr": mock_mgr_handler},
        )

        assert escalation.can_handle("Any issue") is True

    def test_can_handle_board_fallback(self, topology: OrgTopology) -> None:
        """Test can_handle True due to board fallback."""
        escalation = InMemoryOrgEscalation(
            worker_id="dev",
            topology=topology,
            worker_handlers={},  # No handlers
        )

        # Board is always in path, so can_handle is True
        assert escalation.can_handle("Any issue") is True


# ============================================================================
# InMemoryBoardEscalation Tests
# ============================================================================


class TestInMemoryBoardEscalation:
    """Tests for InMemoryBoardEscalation."""

    def test_ask_records_notification(self) -> None:
        """Test ask records notification."""
        notifications: list[dict] = []
        board = InMemoryBoardEscalation(notifications)

        response = board.ask("Critical issue", {"worker": "dev"})

        assert response.resolved is True
        assert response.escalated_to == "board"
        assert len(notifications) == 1
        assert notifications[0]["issue"] == "Critical issue"

    def test_can_handle_always_true(self) -> None:
        """Test board can always handle."""
        board = InMemoryBoardEscalation([])
        assert board.can_handle("Any issue") is True

    def test_report_is_noop(self) -> None:
        """Test report does nothing."""
        board = InMemoryBoardEscalation([])
        board.report("Test report")  # Should not raise


# ============================================================================
# BoardNotifier Tests
# ============================================================================


class TestBoardNotifier:
    """Tests for BoardNotifier."""

    def test_notify_records_notification(self) -> None:
        """Test notify records the notification."""
        notifier = BoardNotifier()

        notifier.notify("Critical issue", {"worker": "dev"})

        pending = notifier.get_pending_notifications()
        assert len(pending) == 1
        assert pending[0]["issue"] == "Critical issue"

    def test_notify_with_callback(self) -> None:
        """Test notify invokes callback."""
        callback_calls: list[tuple] = []

        def callback(issue: str, context: dict) -> None:
            callback_calls.append((issue, context))

        notifier = BoardNotifier(notification_callback=callback)
        notifier.notify("Alert!", {"urgency": "high"})

        assert len(callback_calls) == 1
        assert callback_calls[0][0] == "Alert!"

    def test_clear_notifications(self) -> None:
        """Test clearing notifications."""
        notifier = BoardNotifier()
        notifier.notify("Issue 1", {})
        notifier.notify("Issue 2", {})

        notifier.clear_notifications()

        assert len(notifier.get_pending_notifications()) == 0


# ============================================================================
# BoardEscalation Tests
# ============================================================================


class TestBoardEscalation:
    """Tests for BoardEscalation."""

    def test_ask_notifies_board(self) -> None:
        """Test ask notifies the board."""
        notifier = BoardNotifier()
        board = BoardEscalation(notifier)

        response = board.ask("Need human help", {"worker": "dev"})

        assert response.resolved is True
        assert response.escalated_to == "board"
        assert "human review" in response.guidance.lower()
        assert len(notifier.get_pending_notifications()) == 1

    def test_can_handle_always_true(self) -> None:
        """Test board can always handle."""
        notifier = BoardNotifier()
        board = BoardEscalation(notifier)

        assert board.can_handle("Any issue") is True


# ============================================================================
# Integration Tests
# ============================================================================


class TestOrgEscalationIntegration:
    """Integration tests for org escalation flow."""

    def test_full_escalation_chain(self) -> None:
        """Test escalation through full org chain to board."""
        # Build standard topology
        topology, workers = build_standard_topology()

        # Create escalation for a developer
        escalation = InMemoryOrgEscalation(
            worker_id="dev-1",
            topology=topology,
            worker_handlers={},  # No handlers - will reach board
        )

        response = escalation.ask("Complex architecture question", {"task_id": "t1"})

        # Should reach board
        assert response.resolved is True
        assert response.escalated_to == "board"
        assert len(escalation.board_notifications) == 1

    def test_escalation_stopped_by_manager(self) -> None:
        """Test escalation stopped when manager resolves."""
        topology, workers = build_standard_topology()

        # Manager can resolve
        mgr_handler = MockEscalation(
            resolve_issues=True,
            default_guidance="I'll handle this.",
            escalated_to_name="eng-manager-1",
        )

        escalation = InMemoryOrgEscalation(
            worker_id="dev-1",
            topology=topology,
            worker_handlers={"eng-manager-1": mgr_handler},
        )

        response = escalation.ask("Simple question", {})

        assert response.resolved is True
        assert response.escalated_to == "eng-manager-1"
        assert len(escalation.board_notifications) == 0  # Didn't reach board

    def test_ceo_reports_to_board(self) -> None:
        """Test CEO escalates directly to board."""
        topology, workers = build_standard_topology()

        escalation = InMemoryOrgEscalation(
            worker_id="ceo",
            topology=topology,
            worker_handlers={},
        )

        # CEO has no boss, so path is just ["board"]
        router = HierarchicalRouter(topology)
        path = router.get_escalation_path("ceo")
        assert path == ["board"]

        response = escalation.ask("Strategic decision needed", {})
        assert response.escalated_to == "board"

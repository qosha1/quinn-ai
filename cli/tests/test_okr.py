"""
Unit tests for OKR (Objectives and Key Results) operations.

Tests the OKR cascade hierarchy (Board -> CEO -> Directors -> Managers -> Workers)
and work item linking for strategic alignment.
"""

import tempfile
from pathlib import Path

import pytest

from cli.core.db import (
    Database,
    init_database,
    SCHEMA_VERSION,
)
from cli.core.queries import (
    # Teams & Workers (for fixtures)
    create_team,
    create_worker,
    # OKRs
    create_okr,
    get_okr,
    update_okr_status,
    get_okrs_by_owner,
    get_child_okrs,
    get_okr_hierarchy,
    get_okr_ancestors,
    OKR,
    OKRTreeNode,
    # Work-OKR Links
    link_work_to_okr,
    unlink_work_from_okr,
    get_work_okr_link,
    get_work_for_okr,
    get_okrs_for_work,
    get_work_for_okr_hierarchy,
    WorkOKRLink,
)


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def team(db):
    """Create a test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def ceo(db, team):
    """Create a CEO worker."""
    return create_worker(db, name="CEO", role="CEO", team_id=team.id, cost=100)


@pytest.fixture
def director(db, team, ceo):
    """Create a director worker."""
    return create_worker(
        db, name="Director", role="Director", team_id=team.id,
        cost=80, manager_id=ceo.id
    )


@pytest.fixture
def manager(db, team, director):
    """Create a manager worker."""
    return create_worker(
        db, name="Manager", role="Manager", team_id=team.id,
        cost=60, manager_id=director.id
    )


@pytest.fixture
def worker(db, team, manager):
    """Create a regular worker."""
    return create_worker(
        db, name="Developer", role="Developer", team_id=team.id,
        cost=50, manager_id=manager.id
    )


class TestOKRCreation:
    """Test OKR creation operations."""

    def test_create_okr(self, db, ceo):
        """Should create a new OKR."""
        okr = create_okr(db, title="Increase Revenue", owner_id=ceo.id)
        assert okr.title == "Increase Revenue"
        assert okr.owner_worker_id == ceo.id
        assert okr.status == "active"
        assert okr.id.startswith("okr-")

    def test_create_okr_with_description(self, db, ceo):
        """Should create OKR with description."""
        okr = create_okr(
            db,
            title="Increase Revenue",
            owner_id=ceo.id,
            description="Grow ARR by 50% this quarter"
        )
        assert okr.description == "Grow ARR by 50% this quarter"

    def test_create_okr_with_parent(self, db, ceo, director):
        """Should create OKR with parent for cascade."""
        parent = create_okr(db, title="Company Growth", owner_id=ceo.id)
        child = create_okr(
            db, title="Engineering Excellence",
            owner_id=director.id, parent_id=parent.id
        )
        assert child.parent_okr_id == parent.id

    def test_create_okr_with_custom_id(self, db, ceo):
        """Should create OKR with custom ID."""
        okr = create_okr(
            db, title="Test OKR", owner_id=ceo.id, okr_id="okr-custom-123"
        )
        assert okr.id == "okr-custom-123"

    def test_create_okr_draft_status(self, db, ceo):
        """Should create OKR with draft status."""
        okr = create_okr(db, title="Draft OKR", owner_id=ceo.id, status="draft")
        assert okr.status == "draft"


class TestOKRRetrieval:
    """Test OKR retrieval operations."""

    def test_get_okr(self, db, ceo):
        """Should get OKR by ID."""
        created = create_okr(db, title="Test OKR", owner_id=ceo.id)
        fetched = get_okr(db, created.id)
        assert fetched is not None
        assert fetched.title == "Test OKR"
        assert fetched.owner_worker_id == ceo.id

    def test_get_okr_not_found(self, db):
        """Should return None for non-existent OKR."""
        result = get_okr(db, "nonexistent-okr")
        assert result is None

    def test_get_okrs_by_owner(self, db, ceo):
        """Should get all OKRs owned by a worker."""
        create_okr(db, title="OKR 1", owner_id=ceo.id)
        create_okr(db, title="OKR 2", owner_id=ceo.id)
        create_okr(db, title="OKR 3", owner_id=ceo.id)

        okrs = get_okrs_by_owner(db, ceo.id)
        assert len(okrs) == 3

    def test_get_okrs_by_owner_empty(self, db, ceo):
        """Should return empty list for worker with no OKRs."""
        okrs = get_okrs_by_owner(db, ceo.id)
        assert okrs == []


class TestOKRStatusUpdate:
    """Test OKR status update operations."""

    def test_update_okr_status_completed(self, db, ceo):
        """Should update OKR status to completed."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        update_okr_status(db, okr.id, "completed")
        fetched = get_okr(db, okr.id)
        assert fetched.status == "completed"

    def test_update_okr_status_cancelled(self, db, ceo):
        """Should update OKR status to cancelled."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        update_okr_status(db, okr.id, "cancelled")
        fetched = get_okr(db, okr.id)
        assert fetched.status == "cancelled"


class TestOKRHierarchy:
    """Test OKR cascade hierarchy operations."""

    def test_get_child_okrs(self, db, ceo, director):
        """Should get child OKRs."""
        parent = create_okr(db, title="Company Growth", owner_id=ceo.id)
        child1 = create_okr(
            db, title="Engineering Excellence",
            owner_id=director.id, parent_id=parent.id
        )
        child2 = create_okr(
            db, title="Product Innovation",
            owner_id=director.id, parent_id=parent.id
        )

        children = get_child_okrs(db, parent.id)
        assert len(children) == 2
        child_ids = {c.id for c in children}
        assert child1.id in child_ids
        assert child2.id in child_ids

    def test_get_child_okrs_empty(self, db, ceo):
        """Should return empty list for OKR with no children."""
        okr = create_okr(db, title="Leaf OKR", owner_id=ceo.id)
        children = get_child_okrs(db, okr.id)
        assert children == []

    def test_get_okr_hierarchy(self, db, ceo, director, manager):
        """Should build complete OKR hierarchy tree."""
        # Create hierarchy: CEO -> Director -> Manager
        root = create_okr(db, title="Company Goals", owner_id=ceo.id)
        dir_okr = create_okr(
            db, title="Dept Goals", owner_id=director.id, parent_id=root.id
        )
        mgr_okr = create_okr(
            db, title="Team Goals", owner_id=manager.id, parent_id=dir_okr.id
        )

        tree = get_okr_hierarchy(db, root.id)
        assert tree is not None
        assert tree.okr.id == root.id
        assert len(tree.children) == 1
        assert tree.children[0].okr.id == dir_okr.id
        assert len(tree.children[0].children) == 1
        assert tree.children[0].children[0].okr.id == mgr_okr.id

    def test_get_okr_hierarchy_not_found(self, db):
        """Should return None for non-existent root OKR."""
        tree = get_okr_hierarchy(db, "nonexistent")
        assert tree is None

    def test_get_okr_ancestors(self, db, ceo, director, manager):
        """Should get all ancestor OKRs up to root."""
        # Create hierarchy: CEO -> Director -> Manager
        root = create_okr(db, title="Company Goals", owner_id=ceo.id)
        dir_okr = create_okr(
            db, title="Dept Goals", owner_id=director.id, parent_id=root.id
        )
        mgr_okr = create_okr(
            db, title="Team Goals", owner_id=manager.id, parent_id=dir_okr.id
        )

        ancestors = get_okr_ancestors(db, mgr_okr.id)
        assert len(ancestors) == 2
        assert ancestors[0].id == dir_okr.id  # immediate parent first
        assert ancestors[1].id == root.id

    def test_get_okr_ancestors_root(self, db, ceo):
        """Should return empty list for root OKR."""
        root = create_okr(db, title="Root OKR", owner_id=ceo.id)
        ancestors = get_okr_ancestors(db, root.id)
        assert ancestors == []


class TestOKRCascade:
    """Test full OKR cascade from Board to Workers."""

    def test_full_cascade(self, db, ceo, director, manager, worker):
        """Should support full OKR cascade hierarchy."""
        # Board level OKR
        board_okr = create_okr(db, title="10x Revenue Growth", owner_id=ceo.id)

        # CEO cascades to director
        ceo_okr = create_okr(
            db, title="Scale Engineering",
            owner_id=ceo.id, parent_id=board_okr.id
        )

        # Director cascades to manager
        dir_okr = create_okr(
            db, title="Ship v2.0",
            owner_id=director.id, parent_id=ceo_okr.id
        )

        # Manager cascades to worker
        mgr_okr = create_okr(
            db, title="Build Auth System",
            owner_id=manager.id, parent_id=dir_okr.id
        )

        # Worker level OKR
        worker_okr = create_okr(
            db, title="Implement OAuth2",
            owner_id=worker.id, parent_id=mgr_okr.id
        )

        # Verify hierarchy
        tree = get_okr_hierarchy(db, board_okr.id)
        assert tree is not None

        # Verify depth
        ancestors = get_okr_ancestors(db, worker_okr.id)
        assert len(ancestors) == 4


class TestWorkOKRLinks:
    """Test work item to OKR linking operations."""

    def test_link_work_to_okr(self, db, ceo):
        """Should link work item to OKR."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        link = link_work_to_okr(db, work_id="bead-123", okr_id=okr.id)

        assert link.work_id == "bead-123"
        assert link.okr_id == okr.id
        assert link.link_type == "contributes"

    def test_link_work_to_okr_blocks(self, db, ceo):
        """Should create blocking link."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        link = link_work_to_okr(
            db, work_id="bead-123", okr_id=okr.id, link_type="blocks"
        )
        assert link.link_type == "blocks"

    def test_link_work_to_okr_depends_on(self, db, ceo):
        """Should create dependency link."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        link = link_work_to_okr(
            db, work_id="bead-123", okr_id=okr.id, link_type="depends_on"
        )
        assert link.link_type == "depends_on"

    def test_unlink_work_from_okr(self, db, ceo):
        """Should remove link between work and OKR."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        link_work_to_okr(db, work_id="bead-123", okr_id=okr.id)

        result = unlink_work_from_okr(db, work_id="bead-123", okr_id=okr.id)
        assert result is True

        link = get_work_okr_link(db, work_id="bead-123", okr_id=okr.id)
        assert link is None

    def test_unlink_work_from_okr_not_found(self, db, ceo):
        """Should return False for non-existent link."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        result = unlink_work_from_okr(db, work_id="nonexistent", okr_id=okr.id)
        assert result is False

    def test_get_work_okr_link(self, db, ceo):
        """Should get specific work-OKR link."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        link_work_to_okr(db, work_id="bead-123", okr_id=okr.id)

        link = get_work_okr_link(db, work_id="bead-123", okr_id=okr.id)
        assert link is not None
        assert link.work_id == "bead-123"

    def test_get_work_okr_link_not_found(self, db, ceo):
        """Should return None for non-existent link."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        link = get_work_okr_link(db, work_id="nonexistent", okr_id=okr.id)
        assert link is None

    def test_get_work_for_okr(self, db, ceo):
        """Should get all work items linked to an OKR."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        link_work_to_okr(db, work_id="bead-1", okr_id=okr.id)
        link_work_to_okr(db, work_id="bead-2", okr_id=okr.id)
        link_work_to_okr(db, work_id="bead-3", okr_id=okr.id)

        links = get_work_for_okr(db, okr.id)
        assert len(links) == 3
        work_ids = {l.work_id for l in links}
        assert "bead-1" in work_ids
        assert "bead-2" in work_ids
        assert "bead-3" in work_ids

    def test_get_work_for_okr_empty(self, db, ceo):
        """Should return empty list for OKR with no linked work."""
        okr = create_okr(db, title="Test OKR", owner_id=ceo.id)
        links = get_work_for_okr(db, okr.id)
        assert links == []

    def test_get_okrs_for_work(self, db, ceo):
        """Should get all OKRs linked to a work item."""
        okr1 = create_okr(db, title="OKR 1", owner_id=ceo.id)
        okr2 = create_okr(db, title="OKR 2", owner_id=ceo.id)
        okr3 = create_okr(db, title="OKR 3", owner_id=ceo.id)

        link_work_to_okr(db, work_id="bead-123", okr_id=okr1.id)
        link_work_to_okr(db, work_id="bead-123", okr_id=okr2.id)
        link_work_to_okr(db, work_id="bead-123", okr_id=okr3.id)

        links = get_okrs_for_work(db, "bead-123")
        assert len(links) == 3

    def test_get_okrs_for_work_empty(self, db):
        """Should return empty list for work with no linked OKRs."""
        links = get_okrs_for_work(db, "bead-nonexistent")
        assert links == []


class TestWorkOKRHierarchy:
    """Test work-OKR hierarchy operations."""

    def test_get_work_for_okr_hierarchy(self, db, ceo, director, manager):
        """Should get all work for OKR hierarchy."""
        # Create hierarchy
        root = create_okr(db, title="Company Goals", owner_id=ceo.id)
        dir_okr = create_okr(
            db, title="Dept Goals", owner_id=director.id, parent_id=root.id
        )
        mgr_okr = create_okr(
            db, title="Team Goals", owner_id=manager.id, parent_id=dir_okr.id
        )

        # Link work to each level
        link_work_to_okr(db, work_id="bead-root", okr_id=root.id)
        link_work_to_okr(db, work_id="bead-dir", okr_id=dir_okr.id)
        link_work_to_okr(db, work_id="bead-mgr-1", okr_id=mgr_okr.id)
        link_work_to_okr(db, work_id="bead-mgr-2", okr_id=mgr_okr.id)

        # Get all work for hierarchy
        all_links = get_work_for_okr_hierarchy(db, root.id)
        assert len(all_links) == 4

        work_ids = {l.work_id for l in all_links}
        assert "bead-root" in work_ids
        assert "bead-dir" in work_ids
        assert "bead-mgr-1" in work_ids
        assert "bead-mgr-2" in work_ids

    def test_get_work_for_okr_hierarchy_leaf(self, db, manager):
        """Should get work for leaf OKR (no children)."""
        okr = create_okr(db, title="Leaf OKR", owner_id=manager.id)
        link_work_to_okr(db, work_id="bead-1", okr_id=okr.id)

        all_links = get_work_for_okr_hierarchy(db, okr.id)
        assert len(all_links) == 1
        assert all_links[0].work_id == "bead-1"

    def test_get_work_for_okr_hierarchy_empty(self, db, ceo):
        """Should return empty for hierarchy with no work."""
        root = create_okr(db, title="Root", owner_id=ceo.id)
        child = create_okr(
            db, title="Child", owner_id=ceo.id, parent_id=root.id
        )

        all_links = get_work_for_okr_hierarchy(db, root.id)
        assert all_links == []


class TestOKRStrategicAlignment:
    """Test strategic alignment scenarios."""

    def test_work_contributes_to_multiple_okrs(self, db, ceo, director):
        """Work can contribute to multiple OKRs (e.g., cross-functional)."""
        okr1 = create_okr(db, title="Revenue Growth", owner_id=ceo.id)
        okr2 = create_okr(db, title="Customer Satisfaction", owner_id=director.id)

        link_work_to_okr(db, work_id="feature-xyz", okr_id=okr1.id)
        link_work_to_okr(db, work_id="feature-xyz", okr_id=okr2.id)

        links = get_okrs_for_work(db, "feature-xyz")
        assert len(links) == 2

    def test_okr_with_mixed_link_types(self, db, ceo):
        """OKR can have work with different link types."""
        okr = create_okr(db, title="Launch Product", owner_id=ceo.id)

        link_work_to_okr(db, work_id="bead-build", okr_id=okr.id, link_type="contributes")
        link_work_to_okr(db, work_id="bead-blocker", okr_id=okr.id, link_type="blocks")
        link_work_to_okr(db, work_id="bead-dep", okr_id=okr.id, link_type="depends_on")

        links = get_work_for_okr(db, okr.id)
        assert len(links) == 3

        link_types = {l.link_type for l in links}
        assert link_types == {"contributes", "blocks", "depends_on"}


class TestSchemaVersion:
    """Test schema version update."""

    def test_schema_version_includes_okr(self, db):
        """Schema version should be 9 or higher with OKR tables."""
        assert SCHEMA_VERSION >= 9


class TestKeyResults:
    """Test key results functionality."""

    def test_create_okr_with_key_results(self, db, ceo):
        """OKR can be created with key results."""
        from cli.core.queries import KeyResult

        key_results = [
            KeyResult(metric="test_coverage", target=80, current=0, unit="%"),
            KeyResult(metric="bugs_fixed", target=10, current=0, unit="count"),
        ]
        okr = create_okr(
            db,
            title="Q1 Quality Goals",
            owner_id=ceo.id,
            key_results=key_results,
        )
        assert len(okr.key_results) == 2
        assert okr.key_results[0].metric == "test_coverage"
        assert okr.key_results[0].target == 80
        assert okr.key_results[1].metric == "bugs_fixed"

    def test_get_okr_with_key_results(self, db, ceo):
        """Retrieved OKR includes key results."""
        from cli.core.queries import KeyResult

        key_results = [KeyResult(metric="lighthouse", target=90, current=75, unit="score")]
        created = create_okr(db, title="Performance OKR", owner_id=ceo.id, key_results=key_results)

        fetched = get_okr(db, created.id)
        assert len(fetched.key_results) == 1
        assert fetched.key_results[0].metric == "lighthouse"
        assert fetched.key_results[0].current == 75

    def test_update_key_result(self, db, ceo):
        """Key result current value can be updated."""
        from cli.core.queries import KeyResult, update_okr_key_result

        key_results = [KeyResult(metric="test_coverage", target=80, current=50, unit="%")]
        okr = create_okr(db, title="Coverage OKR", owner_id=ceo.id, key_results=key_results)

        updated = update_okr_key_result(db, okr.id, "test_coverage", 72)
        assert updated is not None
        assert updated.key_results[0].current == 72

    def test_update_nonexistent_key_result(self, db, ceo):
        """Updating nonexistent key result returns None."""
        from cli.core.queries import KeyResult, update_okr_key_result

        key_results = [KeyResult(metric="test_coverage", target=80, current=50, unit="%")]
        okr = create_okr(db, title="Coverage OKR", owner_id=ceo.id, key_results=key_results)

        result = update_okr_key_result(db, okr.id, "nonexistent", 72)
        assert result is None

    def test_add_key_result(self, db, ceo):
        """Key result can be added to existing OKR."""
        from cli.core.queries import add_okr_key_result

        okr = create_okr(db, title="Empty OKR", owner_id=ceo.id)
        assert len(okr.key_results) == 0

        updated = add_okr_key_result(db, okr.id, "bugs_fixed", 10, "count", 3)
        assert updated is not None
        assert len(updated.key_results) == 1
        assert updated.key_results[0].metric == "bugs_fixed"
        assert updated.key_results[0].target == 10
        assert updated.key_results[0].current == 3

    def test_add_duplicate_key_result_fails(self, db, ceo):
        """Adding duplicate key result metric returns None."""
        from cli.core.queries import KeyResult, add_okr_key_result

        key_results = [KeyResult(metric="test_coverage", target=80, current=50, unit="%")]
        okr = create_okr(db, title="Coverage OKR", owner_id=ceo.id, key_results=key_results)

        result = add_okr_key_result(db, okr.id, "test_coverage", 90, "%", 0)
        assert result is None


class TestOKRProgress:
    """Test OKR progress calculation."""

    def test_key_result_progress(self, db, ceo):
        """Key result progress is calculated correctly."""
        from cli.core.queries import KeyResult

        kr = KeyResult(metric="test", target=100, current=75, unit="%")
        assert kr.progress() == 75.0
        assert not kr.is_met()

        kr.current = 100
        assert kr.progress() == 100.0
        assert kr.is_met()

    def test_key_result_progress_exceeds_target(self, db, ceo):
        """Progress caps at 100% when exceeding target."""
        from cli.core.queries import KeyResult

        kr = KeyResult(metric="test", target=80, current=100, unit="%")
        assert kr.progress() == 100.0  # Capped at 100%
        assert kr.is_met()

    def test_okr_overall_progress(self, db, ceo):
        """OKR overall progress averages all key results."""
        from cli.core.queries import KeyResult

        key_results = [
            KeyResult(metric="kr1", target=100, current=50, unit="%"),  # 50%
            KeyResult(metric="kr2", target=100, current=100, unit="%"),  # 100%
        ]
        okr = create_okr(db, title="Progress OKR", owner_id=ceo.id, key_results=key_results)

        assert okr.progress() == 75.0  # Average of 50% and 100%

    def test_okr_all_key_results_met(self, db, ceo):
        """OKR reports when all key results are met."""
        from cli.core.queries import KeyResult

        key_results = [
            KeyResult(metric="kr1", target=80, current=80, unit="%"),
            KeyResult(metric="kr2", target=10, current=15, unit="count"),
        ]
        okr = create_okr(db, title="Complete OKR", owner_id=ceo.id, key_results=key_results)

        assert okr.all_key_results_met()

    def test_okr_not_all_key_results_met(self, db, ceo):
        """OKR reports when not all key results are met."""
        from cli.core.queries import KeyResult

        key_results = [
            KeyResult(metric="kr1", target=80, current=80, unit="%"),
            KeyResult(metric="kr2", target=10, current=5, unit="count"),
        ]
        okr = create_okr(db, title="Incomplete OKR", owner_id=ceo.id, key_results=key_results)

        assert not okr.all_key_results_met()

    def test_empty_okr_progress(self, db, ceo):
        """OKR with no key results has 0% progress."""
        okr = create_okr(db, title="Empty OKR", owner_id=ceo.id)
        assert okr.progress() == 0.0
        assert not okr.all_key_results_met()


class TestOKRDueDate:
    """Test OKR due date functionality."""

    def test_create_okr_with_due_date(self, db, ceo):
        """OKR can be created with due date."""
        from datetime import date

        due = date(2025, 3, 31)
        okr = create_okr(db, title="Q1 OKR", owner_id=ceo.id, due_date=due)
        assert okr.due_date == due

    def test_get_okr_with_due_date(self, db, ceo):
        """Retrieved OKR includes due date."""
        from datetime import date

        due = date(2025, 6, 30)
        created = create_okr(db, title="Q2 OKR", owner_id=ceo.id, due_date=due)

        fetched = get_okr(db, created.id)
        assert fetched.due_date == due

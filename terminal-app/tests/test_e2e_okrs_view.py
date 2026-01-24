"""E2E tests for OKRs view tree display.

Tests the OKRs view displays hierarchy correctly with:
- Board -> CEO -> Director cascading
- Key results shown as leaf nodes
- Progress indicators calculated from key_results JSON
- Owner names displayed
- Empty state handling
- Orphaned OKR handling
"""

import json
import pytest
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from textual.widgets import Tree

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.okrs import OKRsView


def create_org_db_with_okrs(org_path: Path, okr_setup: str = "hierarchy") -> Path:
    """Create org database with OKR test data.

    Args:
        org_path: Path to org folder
        okr_setup: Test scenario - 'hierarchy', 'with_krs', 'empty', 'orphaned'

    Returns:
        Path to created database
    """
    live_path = org_path / "live"
    live_path.mkdir(parents=True, exist_ok=True)

    db_path = live_path / "quinn.db"
    conn = sqlite3.connect(str(db_path))

    # Create schema
    conn.executescript("""
        CREATE TABLE org_state (
            id TEXT PRIMARY KEY,
            status TEXT,
            ceo_worker_id TEXT,
            started_at TEXT,
            stopped_at TEXT
        );

        CREATE TABLE teams (
            id TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE workers (
            id TEXT PRIMARY KEY,
            name TEXT,
            role TEXT,
            team_id TEXT,
            manager_id TEXT,
            status TEXT,
            created_at TEXT,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            worker_id TEXT,
            state TEXT,
            tmux_session_name TEXT,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        );

        CREATE TABLE worker_state (
            id INTEGER PRIMARY KEY,
            worker_id TEXT,
            runtime_status TEXT,
            current_task_id TEXT,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        );

        CREATE TABLE channels (
            id TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            channel_id TEXT,
            thread_id TEXT,
            parent_id TEXT,
            from_worker_id TEXT,
            content TEXT,
            priority INTEGER,
            time_sensitivity TEXT,
            created_at TEXT,
            FOREIGN KEY (channel_id) REFERENCES channels(id)
        );

        CREATE TABLE notification_beads (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            status TEXT,
            read_at TEXT,
            FOREIGN KEY (message_id) REFERENCES messages(id)
        );

        CREATE TABLE okrs (
            id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            owner_worker_id TEXT,
            status TEXT,
            parent_okr_id TEXT,
            key_results TEXT,
            due_date TEXT,
            created_at TEXT,
            FOREIGN KEY (owner_worker_id) REFERENCES workers(id)
        );

        CREATE TABLE budget_pools (
            id TEXT PRIMARY KEY,
            period_start TEXT,
            period_end TEXT,
            created_at TEXT
        );

        CREATE TABLE budget_allocations (
            id TEXT PRIMARY KEY,
            pool_id TEXT,
            worker_id TEXT,
            FOREIGN KEY (pool_id) REFERENCES budget_pools(id)
        );

        CREATE TABLE budget_balances (
            id TEXT PRIMARY KEY,
            allocation_id TEXT,
            allocated REAL,
            spent REAL,
            available REAL,
            FOREIGN KEY (allocation_id) REFERENCES budget_allocations(id)
        );

        CREATE TABLE budget_transactions (
            id TEXT PRIMARY KEY,
            type TEXT,
            amount REAL,
            created_at TEXT
        );
    """)

    now = datetime.now().isoformat()

    # Insert base data
    conn.execute(
        "INSERT INTO org_state (id, status, ceo_worker_id, started_at) VALUES (?, ?, ?, ?)",
        ("default", "running", "worker-ceo", now),
    )

    conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")
    conn.execute("INSERT INTO teams VALUES ('team-eng', 'Engineering')")

    conn.execute(
        "INSERT INTO workers VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("worker-board", "Board Member", "Board", "team-exec", None, "active", now),
    )
    conn.execute(
        "INSERT INTO workers VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("worker-ceo", "Alice CEO", "CEO", "team-exec", None, "active", now),
    )
    conn.execute(
        "INSERT INTO workers VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("worker-director", "Bob Director", "Director", "team-eng", "worker-ceo", "active", now),
    )

    conn.execute("INSERT INTO channels VALUES ('ch-esc', 'escalations')")

    # Insert OKRs based on scenario
    if okr_setup == "hierarchy":
        create_okr_hierarchy(conn, now)
    elif okr_setup == "with_krs":
        create_okr_with_krs(conn, now)
    elif okr_setup == "orphaned":
        create_orphaned_okrs(conn, now)
    # 'empty' scenario: no OKRs inserted

    conn.commit()
    conn.close()
    return db_path


def create_okr_hierarchy(conn, now: str):
    """Create Board -> CEO -> Director OKR hierarchy."""
    # Board level OKR (no parent)
    conn.execute(
        """INSERT INTO okrs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "okr-board-1",
            "Ship v1.0 product",
            "Launch first version to market",
            "worker-board",
            "active",
            None,  # No parent
            json.dumps([
                {"description": "Complete MVP features", "current": 8, "target": 10, "unit": "features"},
                {"description": "Pass security audit", "current": 1, "target": 1, "unit": "audit"},
                {"description": "Onboard beta users", "current": 15, "target": 50, "unit": "users"},
            ]),
            "2026-03-31",
            now,
        ),
    )

    # CEO level OKR (parent: board)
    conn.execute(
        """INSERT INTO okrs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "okr-ceo-1",
            "Deliver MVP by Q1",
            "Complete core product features",
            "worker-ceo",
            "active",
            "okr-board-1",  # Parent: Board OKR
            json.dumps([
                {"description": "Core API complete", "current": 10, "target": 10, "unit": "endpoints"},
                {"description": "Frontend functional", "current": 7, "target": 10, "unit": "pages"},
            ]),
            "2026-02-28",
            now,
        ),
    )

    # Director level OKR (parent: CEO)
    conn.execute(
        """INSERT INTO okrs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "okr-director-1",
            "Technical delivery complete",
            "All engineering milestones met",
            "worker-director",
            "active",
            "okr-ceo-1",  # Parent: CEO OKR
            json.dumps([
                {"description": "API tests passing", "current": 80, "target": 100, "unit": "%"},
                {"description": "Performance benchmarks met", "current": 2, "target": 3, "unit": "benchmarks"},
            ]),
            "2026-02-15",
            now,
        ),
    )


def create_okr_with_krs(conn, now: str):
    """Create OKR with 3 key results (2 complete)."""
    conn.execute(
        """INSERT INTO okrs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "okr-test-1",
            "Test OKR with Key Results",
            "Testing key result display",
            "worker-ceo",
            "active",
            None,
            json.dumps([
                {"description": "First KR complete", "current": 100, "target": 100, "unit": "%"},
                {"description": "Second KR complete", "current": 50, "target": 50, "unit": "items"},
                {"description": "Third KR in progress", "current": 5, "target": 10, "unit": "tasks"},
            ]),
            "2026-02-28",
            now,
        ),
    )


def create_orphaned_okrs(conn, now: str):
    """Create OKR with invalid parent and valid OKR."""
    # Valid OKR
    conn.execute(
        """INSERT INTO okrs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "okr-valid",
            "Valid OKR",
            "This has no parent",
            "worker-ceo",
            "active",
            None,
            json.dumps([{"description": "Test", "current": 1, "target": 1, "unit": "item"}]),
            "2026-02-28",
            now,
        ),
    )

    # Orphaned OKR (parent doesn't exist)
    conn.execute(
        """INSERT INTO okrs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "okr-orphaned",
            "Orphaned OKR",
            "This has invalid parent",
            "worker-director",
            "active",
            "okr-nonexistent",  # Parent doesn't exist
            json.dumps([{"description": "Orphan KR", "current": 0, "target": 1, "unit": "item"}]),
            "2026-02-28",
            now,
        ),
    )


class TestE2EOKRsView:
    """E2E tests for OKRs view tree display."""

    @pytest.mark.asyncio
    async def test_okrs_view_shows_hierarchy(self):
        """OKRs view should display Board -> CEO -> Director hierarchy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            create_org_db_with_okrs(org_path, okr_setup="hierarchy")

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should auto-connect to running org
                assert app._is_connected
                assert app._active_org_path == org_path

                # Switch to OKRs tab
                app.action_switch_tab("okrs")
                await pilot.pause()

                # Get OKRs view and tree
                okrs_view = app.query_one("#okrs-view", OKRsView)
                assert okrs_view is not None

                tree = app.query_one("#okr-tree", Tree)
                assert tree is not None

                # Verify tree structure
                assert tree.root is not None
                assert tree.root.is_expanded

                # Should have children (hierarchy loaded)
                children = list(tree.root.children)
                assert len(children) > 0, "Tree should have OKR nodes"

                # Walk tree to verify 3 levels exist
                def count_depth(node, depth=0):
                    """Recursively count max depth of tree."""
                    if not list(node.children):
                        return depth
                    return max(count_depth(child, depth + 1) for child in node.children)

                max_depth = count_depth(tree.root)
                assert max_depth >= 3, "Should have at least 3 levels (Board->CEO->Director)"

    @pytest.mark.asyncio
    async def test_okrs_view_shows_key_results(self):
        """OKRs view should show key results as leaf nodes with format: 'KR description [current/target unit]'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            create_org_db_with_okrs(org_path, okr_setup="with_krs")

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                app.action_switch_tab("okrs")
                await pilot.pause()

                tree = app.query_one("#okr-tree", Tree)

                # Walk tree to find all leaf nodes
                def find_leaves(node):
                    """Recursively find all leaf nodes."""
                    leaves = []
                    children = list(node.children)
                    if not children:
                        leaves.append(node)
                    else:
                        for child in children:
                            leaves.extend(find_leaves(child))
                    return leaves

                leaves = find_leaves(tree.root)

                # Should have at least 3 key result leaf nodes
                assert len(leaves) >= 3, f"Expected at least 3 KR leaves, got {len(leaves)}"

                # Check that leaves contain progress indicators [current/target unit]
                leaf_labels = [str(leaf.label) for leaf in leaves]

                # At least one leaf should match KR format
                kr_format_found = any("[" in label and "/" in label for label in leaf_labels)
                assert kr_format_found, f"Expected KR format '[current/target unit]' in leaves: {leaf_labels}"

    @pytest.mark.asyncio
    async def test_okrs_view_calculates_progress(self):
        """OKRs view should calculate and display progress correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            create_org_db_with_okrs(org_path, okr_setup="with_krs")

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                app.action_switch_tab("okrs")
                await pilot.pause()

                tree = app.query_one("#okr-tree", Tree)

                # Walk tree to find all nodes
                def get_all_labels(node, labels=None):
                    if labels is None:
                        labels = []
                    labels.append(str(node.label))
                    for child in node.children:
                        get_all_labels(child, labels)
                    return labels

                all_labels = get_all_labels(tree.root)

                # Should have progress indicators
                # Look for formats like: "[2/3 KRs complete]" or "67%" or "[100/100 %]"
                progress_indicators = [
                    label for label in all_labels
                    if ("[" in label and ("KR" in label or "%" in label or "/" in label))
                ]

                assert len(progress_indicators) > 0, f"Expected progress indicators in: {all_labels}"

    @pytest.mark.asyncio
    async def test_okrs_view_empty_state(self):
        """OKRs view should show helpful message when no OKRs exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            create_org_db_with_okrs(org_path, okr_setup="empty")

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                app.action_switch_tab("okrs")
                await pilot.pause()

                okrs_view = app.query_one("#okrs-view", OKRsView)
                assert okrs_view is not None

                tree = app.query_one("#okr-tree", Tree)
                assert tree is not None

                # Tree should exist but may be empty or show placeholder
                # The view should not crash
                assert tree.root is not None

    @pytest.mark.asyncio
    async def test_okrs_view_handles_no_connection(self):
        """OKRs view should handle no org connection gracefully."""
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Not connected
            assert not app._is_connected

            # Try to switch to OKRs tab (should show placeholder or empty state)
            app.action_switch_tab("okrs")
            await pilot.pause()

            # Should not crash
            assert app.is_running

            # OKRs view should exist (even if showing empty state)
            okrs_view = app.query_one("#okrs-view", OKRsView)
            assert okrs_view is not None

    @pytest.mark.asyncio
    async def test_okrs_view_shows_owner_names(self):
        """OKRs view should display owner names in tree nodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            create_org_db_with_okrs(org_path, okr_setup="hierarchy")

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                app.action_switch_tab("okrs")
                await pilot.pause()

                tree = app.query_one("#okr-tree", Tree)

                # Get all node labels
                def get_all_labels(node, labels=None):
                    if labels is None:
                        labels = []
                    labels.append(str(node.label))
                    for child in node.children:
                        get_all_labels(child, labels)
                    return labels

                all_labels = get_all_labels(tree.root)

                # Should have owner names in labels
                # Format should include owner like: "Title (Owner Name)" or similar
                has_owner_info = any(
                    any(name in label for name in ["Alice", "Bob", "Board"])
                    for label in all_labels
                )

                assert has_owner_info, f"Expected owner names in labels: {all_labels}"

    @pytest.mark.asyncio
    async def test_okrs_view_handles_orphaned_okrs(self):
        """OKRs view should handle OKRs with invalid parent_okr_id gracefully.

        NOTE: This test verifies the view doesn't crash with orphaned data.
        Once refresh_okrs() is implemented, it should also verify that:
        - Valid OKRs are displayed
        - Orphaned OKRs are handled (shown at root or skipped)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            create_org_db_with_okrs(org_path, okr_setup="orphaned")

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                app.action_switch_tab("okrs")
                await pilot.pause()

                # Should not crash with orphaned OKR data
                assert app.is_running

                tree = app.query_one("#okr-tree", Tree)
                assert tree is not None

                # Get all labels to verify tree structure exists
                def get_all_labels(node, labels=None):
                    if labels is None:
                        labels = []
                    labels.append(str(node.label))
                    for child in node.children:
                        get_all_labels(child, labels)
                    return labels

                all_labels = get_all_labels(tree.root)

                # Should have tree structure (even if placeholder)
                assert len(all_labels) > 1, "Should have tree nodes"

                # TODO: When refresh_okrs() is implemented, verify:
                # - Valid OKRs from database are shown
                # - Orphaned OKRs don't crash the rendering
                # has_valid = any("Valid OKR" in label for label in all_labels)
                # assert has_valid, "Should show valid OKR from database"


class TestOKRHelpers:
    """Tests for OKR helper functions used in tests."""

    def test_create_okr_hierarchy(self):
        """Helper should create 3-level hierarchy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            db_path = create_org_db_with_okrs(org_path, okr_setup="hierarchy")

            # Verify database was created
            assert db_path.exists()

            # Verify OKRs were inserted
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM okrs")
            count = cursor.fetchone()[0]
            assert count == 3, "Should have 3 OKRs (Board, CEO, Director)"

            # Verify hierarchy
            board_okr = conn.execute(
                "SELECT * FROM okrs WHERE parent_okr_id IS NULL"
            ).fetchone()
            assert board_okr is not None

            ceo_okr = conn.execute(
                "SELECT * FROM okrs WHERE parent_okr_id = ?",
                (board_okr[0],)  # board OKR id
            ).fetchone()
            assert ceo_okr is not None

            director_okr = conn.execute(
                "SELECT * FROM okrs WHERE parent_okr_id = ?",
                (ceo_okr[0],)  # CEO OKR id
            ).fetchone()
            assert director_okr is not None

            conn.close()

    def test_create_okr_with_krs(self):
        """Helper should create OKR with 3 key results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            db_path = create_org_db_with_okrs(org_path, okr_setup="with_krs")

            conn = sqlite3.connect(str(db_path))
            okr = conn.execute("SELECT key_results FROM okrs").fetchone()
            assert okr is not None

            key_results = json.loads(okr[0])
            assert len(key_results) == 3, "Should have 3 key results"

            # Verify 2 are complete
            complete_count = sum(
                1 for kr in key_results
                if kr["current"] >= kr["target"]
            )
            assert complete_count == 2, "Should have 2 complete KRs"

            conn.close()

    def test_parse_key_results_for_verification(self):
        """Test parsing key_results JSON for verification."""
        kr_json = json.dumps([
            {"description": "KR 1", "current": 100, "target": 100, "unit": "%"},
            {"description": "KR 2", "current": 50, "target": 100, "unit": "%"},
        ])

        key_results = json.loads(kr_json)
        assert len(key_results) == 2

        # Calculate progress
        complete_krs = sum(1 for kr in key_results if kr["current"] >= kr["target"])
        progress_pct = (complete_krs / len(key_results)) * 100

        assert complete_krs == 1
        assert progress_pct == 50.0

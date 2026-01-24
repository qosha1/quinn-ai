"""E2E tests for Dashboard view data display.

Tests full dashboard rendering with real org data, including fallback
behavior when budget_balances are missing (broken state).
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

from textual.widgets import Label

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.dashboard import DashboardView


def get_label_text(label: Label) -> str:
    """Helper to get text content from a Label widget."""
    return str(label.render())


@pytest.fixture
def org_with_budget_balances():
    """Create org with properly initialized budget_balances.

    This is the correct/happy path state where budget_balances table
    is properly populated.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-with-balances"
        org_path.mkdir()
        live_path = org_path / "live"
        live_path.mkdir()

        db_path = live_path / "quinn.db"
        conn = sqlite3.connect(str(db_path))

        # Create all required tables
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

        # Insert test data
        now = datetime.now()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=30)

        conn.execute("""
            INSERT INTO org_state (id, status, ceo_worker_id, started_at)
            VALUES ('default', 'running', 'worker-ceo', ?)
        """, (now.isoformat(),))

        conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")
        conn.execute("INSERT INTO teams VALUES ('team-eng', 'Engineering')")

        conn.execute("""
            INSERT INTO workers VALUES
            ('worker-ceo', 'Alice', 'CEO', 'team-exec', NULL, 'active', ?)
        """, (now.isoformat(),))
        conn.execute("""
            INSERT INTO workers VALUES
            ('worker-dev1', 'Bob', 'Developer', 'team-eng', 'worker-ceo', 'active', ?)
        """, (now.isoformat(),))

        conn.execute("""
            INSERT INTO sessions VALUES
            ('session-ceo', 'worker-ceo', 'running', 'org-test-org-ceo')
        """)
        conn.execute("""
            INSERT INTO sessions VALUES
            ('session-dev1', 'worker-dev1', 'idle', 'org-test-org-dev1')
        """)

        conn.execute("INSERT INTO channels VALUES ('ch-esc', 'escalations')")

        # Add unread messages
        conn.execute("""
            INSERT INTO messages VALUES
            ('msg-1', 'ch-esc', NULL, NULL, 'worker-dev1', 'Need help with API design', 3, 'normal', ?)
        """, (now.isoformat(),))
        conn.execute("""
            INSERT INTO notification_beads VALUES ('nb-1', 'msg-1', 'pending', NULL)
        """)

        # Create budget pool with balances
        conn.execute("""
            INSERT INTO budget_pools VALUES
            ('pool-1', ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat()))

        conn.execute("""
            INSERT INTO budget_allocations VALUES
            ('alloc-ceo', 'pool-1', 'worker-ceo')
        """)
        conn.execute("""
            INSERT INTO budget_allocations VALUES
            ('alloc-dev1', 'pool-1', 'worker-dev1')
        """)

        # Populate budget_balances (correct state)
        conn.execute("""
            INSERT INTO budget_balances VALUES
            ('bal-ceo', 'alloc-ceo', 100.0, 25.50, 74.50)
        """)
        conn.execute("""
            INSERT INTO budget_balances VALUES
            ('bal-dev1', 'alloc-dev1', 50.0, 12.75, 37.25)
        """)

        # Add spend transactions
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        conn.execute("""
            INSERT INTO budget_transactions VALUES
            ('tx-1', 'spend', -5.25, ?)
        """, (today_start.isoformat(),))
        conn.execute("""
            INSERT INTO budget_transactions VALUES
            ('tx-2', 'spend', -3.10, ?)
        """, ((today_start + timedelta(hours=2)).isoformat(),))

        conn.commit()
        conn.close()

        yield org_path


@pytest.fixture
def org_without_budget_balances():
    """Create org with budget_allocations but NO budget_balances (broken state).

    This tests the fallback behavior when budget_balances table is empty
    or data migration hasn't been run yet.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-broken-budget"
        org_path.mkdir()
        live_path = org_path / "live"
        live_path.mkdir()

        db_path = live_path / "quinn.db"
        conn = sqlite3.connect(str(db_path))

        # Create all required tables
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

        # Insert test data
        now = datetime.now()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=30)

        conn.execute("""
            INSERT INTO org_state (id, status, ceo_worker_id, started_at)
            VALUES ('default', 'running', 'worker-ceo', ?)
        """, (now.isoformat(),))

        conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")

        conn.execute("""
            INSERT INTO workers VALUES
            ('worker-ceo', 'Alice', 'CEO', 'team-exec', NULL, 'active', ?)
        """, (now.isoformat(),))

        conn.execute("""
            INSERT INTO sessions VALUES
            ('session-ceo', 'worker-ceo', 'running', 'org-test-org-ceo')
        """)

        conn.execute("INSERT INTO channels VALUES ('ch-esc', 'escalations')")

        # Create budget pool with allocations but NO balances (broken state)
        conn.execute("""
            INSERT INTO budget_pools VALUES
            ('pool-1', ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat()))

        conn.execute("""
            INSERT INTO budget_allocations VALUES
            ('alloc-ceo', 'pool-1', 'worker-ceo')
        """)

        # IMPORTANT: budget_balances table exists but is EMPTY
        # This is the broken state we're testing

        conn.commit()
        conn.close()

        yield org_path


@pytest.fixture
def org_with_active_workers():
    """Create org with multiple active workers for session count testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-active"
        org_path.mkdir()
        live_path = org_path / "live"
        live_path.mkdir()

        db_path = live_path / "quinn.db"
        conn = sqlite3.connect(str(db_path))

        # Create all required tables
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

        # Insert test data with 3 active workers
        now = datetime.now()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=30)

        conn.execute("""
            INSERT INTO org_state (id, status, ceo_worker_id, started_at)
            VALUES ('default', 'running', 'worker-ceo', ?)
        """, (now.isoformat(),))

        conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")
        conn.execute("INSERT INTO teams VALUES ('team-eng', 'Engineering')")

        # CEO + 2 developers
        conn.execute("""
            INSERT INTO workers VALUES
            ('worker-ceo', 'Alice', 'CEO', 'team-exec', NULL, 'active', ?)
        """, (now.isoformat(),))
        conn.execute("""
            INSERT INTO workers VALUES
            ('worker-dev1', 'Bob', 'Developer', 'team-eng', 'worker-ceo', 'active', ?)
        """, (now.isoformat(),))
        conn.execute("""
            INSERT INTO workers VALUES
            ('worker-dev2', 'Charlie', 'Developer', 'team-eng', 'worker-ceo', 'active', ?)
        """, (now.isoformat(),))

        # All 3 have active sessions
        conn.execute("""
            INSERT INTO sessions VALUES
            ('session-ceo', 'worker-ceo', 'running', 'org-test-org-ceo')
        """)
        conn.execute("""
            INSERT INTO sessions VALUES
            ('session-dev1', 'worker-dev1', 'running', 'org-test-org-dev1')
        """)
        conn.execute("""
            INSERT INTO sessions VALUES
            ('session-dev2', 'worker-dev2', 'idle', 'org-test-org-dev2')
        """)

        conn.execute("INSERT INTO channels VALUES ('ch-esc', 'escalations')")

        # Create budget pool with balances
        conn.execute("""
            INSERT INTO budget_pools VALUES
            ('pool-1', ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat()))

        conn.execute("""
            INSERT INTO budget_allocations VALUES
            ('alloc-ceo', 'pool-1', 'worker-ceo')
        """)

        conn.execute("""
            INSERT INTO budget_balances VALUES
            ('bal-ceo', 'alloc-ceo', 100.0, 0.0, 100.0)
        """)

        conn.commit()
        conn.close()

        yield org_path


class TestE2EDashboard:
    """E2E tests for Dashboard view data display."""

    @pytest.mark.asyncio
    async def test_dashboard_shows_metrics_with_budget_balances(self, org_with_budget_balances):
        """Dashboard should show metrics when budget_balances are populated."""
        config = BoardConfig(org_paths=[org_with_budget_balances.parent])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org
            await app._connect_to_org(org_with_budget_balances)
            await pilot.pause()

            # Switch to dashboard
            app.action_switch_tab("dashboard")
            await pilot.pause()

            # Get dashboard view
            dashboard = app.query_one("#dashboard-view", DashboardView)
            await dashboard.refresh_data()
            await pilot.pause()

            # Verify worker count
            worker_count_label = app.query_one("#worker-count", Label)
            assert get_label_text(worker_count_label) == "2"

            # Verify active sessions count
            active_count_label = app.query_one("#active-count", Label)
            assert get_label_text(active_count_label) in ("2", "1")  # Running + idle sessions

            # Verify budget spend (should show real data, not $0.00)
            spend_label = app.query_one("#spend-today", Label)
            spend_text = get_label_text(spend_label)
            assert "$" in spend_text
            # Should have actual spend data from transactions
            assert spend_text in ("$5.25", "$8.35", "$3.10")  # Individual or combined spend

    @pytest.mark.asyncio
    async def test_dashboard_shows_metrics_without_budget_balances(self, org_without_budget_balances):
        """Dashboard should show fallback metrics when budget_balances are empty."""
        config = BoardConfig(org_paths=[org_without_budget_balances.parent])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org
            await app._connect_to_org(org_without_budget_balances)
            await pilot.pause()

            # Switch to dashboard
            app.action_switch_tab("dashboard")
            await pilot.pause()

            # Get dashboard view
            dashboard = app.query_one("#dashboard-view", DashboardView)
            await dashboard.refresh_data()
            await pilot.pause()

            # Verify fallback works (should show $0.00 because no balances/transactions)
            spend_label = app.query_one("#spend-today", Label)
            spend_text = get_label_text(spend_label)
            assert spend_text == "$0.00"

            # Worker count should still work
            worker_count_label = app.query_one("#worker-count", Label)
            assert get_label_text(worker_count_label) == "1"

    @pytest.mark.asyncio
    async def test_dashboard_updates_on_org_connect(self):
        """Dashboard should refresh when org is connected."""
        # Start with no org
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            org_path.mkdir()
            live_path = org_path / "live"
            live_path.mkdir()

            db_path = live_path / "quinn.db"
            conn = sqlite3.connect(str(db_path))

            # Minimal org setup
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

            now = datetime.now()
            conn.execute("""
                INSERT INTO org_state (id, status, ceo_worker_id, started_at)
                VALUES ('default', 'running', 'worker-ceo', ?)
            """, (now.isoformat(),))

            conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")
            conn.execute("""
                INSERT INTO workers VALUES
                ('worker-ceo', 'TestCEO', 'CEO', 'team-exec', NULL, 'active', ?)
            """, (now.isoformat(),))

            conn.execute("""
                INSERT INTO sessions VALUES
                ('session-ceo', 'worker-ceo', 'running', 'org-test-org-ceo')
            """)

            conn.execute("INSERT INTO channels VALUES ('ch-esc', 'escalations')")

            conn.commit()
            conn.close()

            async with app.run_test() as pilot:
                await pilot.pause()

                # Initially no org connected
                assert app._active_org_path is None

                # Connect to org
                await app._connect_to_org(org_path)
                await pilot.pause()

                # Switch to dashboard
                app.action_switch_tab("dashboard")
                await pilot.pause()

                # Dashboard should show real data
                worker_count_label = app.query_one("#worker-count", Label)
                assert get_label_text(worker_count_label) == "1"

    @pytest.mark.asyncio
    async def test_dashboard_shows_zero_for_new_org(self):
        """Dashboard should show accurate zeros for fresh org with no activity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "fresh-org"
            org_path.mkdir()
            live_path = org_path / "live"
            live_path.mkdir()

            db_path = live_path / "quinn.db"
            conn = sqlite3.connect(str(db_path))

            # Minimal fresh org - no workers, no sessions, no budget
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

            # Uninitialized org state
            conn.execute("""
                INSERT INTO org_state (id, status, ceo_worker_id, started_at)
                VALUES ('default', 'initialized', NULL, NULL)
            """)

            conn.commit()
            conn.close()

            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Connect to fresh org
                await app._connect_to_org(org_path)
                await pilot.pause()

                # Switch to dashboard
                app.action_switch_tab("dashboard")
                await pilot.pause()

                # Dashboard should show zeros (not crash)
                worker_count_label = app.query_one("#worker-count", Label)
                assert get_label_text(worker_count_label) == "0"

                active_count_label = app.query_one("#active-count", Label)
                assert get_label_text(active_count_label) == "0"

                spend_label = app.query_one("#spend-today", Label)
                assert get_label_text(spend_label) == "$0.00"

    @pytest.mark.asyncio
    async def test_dashboard_shows_ceo_status(self, org_with_budget_balances):
        """Dashboard should show CEO card with name, status, role."""
        config = BoardConfig(org_paths=[org_with_budget_balances.parent])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org
            await app._connect_to_org(org_with_budget_balances)
            await pilot.pause()

            # Switch to dashboard
            app.action_switch_tab("dashboard")
            await pilot.pause()

            # Get dashboard view and refresh
            dashboard = app.query_one("#dashboard-view", DashboardView)
            await dashboard.refresh_data()
            await pilot.pause()

            # Verify CEO status is displayed
            ceo_status_label = app.query_one("#ceo-status", Label)
            status_text = get_label_text(ceo_status_label)
            assert "Status:" in status_text
            assert status_text in ("Status: Active", "Status: Inactive")

    @pytest.mark.asyncio
    async def test_dashboard_metric_cards_exist(self, org_with_budget_balances):
        """Dashboard should have all metric widgets present with correct labels."""
        config = BoardConfig(org_paths=[org_with_budget_balances.parent])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org
            await app._connect_to_org(org_with_budget_balances)
            await pilot.pause()

            # Switch to dashboard
            app.action_switch_tab("dashboard")
            await pilot.pause()

            # Verify metric cards exist
            metric_cards = app.query(".metric-card")
            assert len(metric_cards) >= 3  # At least: messages, spend, workers, sessions

            # Verify specific metric elements
            spend_label = app.query_one("#spend-today", Label)
            assert spend_label is not None

            worker_count_label = app.query_one("#worker-count", Label)
            assert worker_count_label is not None

            active_count_label = app.query_one("#active-count", Label)
            assert active_count_label is not None

            unread_count_label = app.query_one("#unread-count", Label)
            assert unread_count_label is not None

    @pytest.mark.asyncio
    async def test_dashboard_shows_active_session_count(self, org_with_active_workers):
        """Dashboard should accurately count active sessions."""
        config = BoardConfig(org_paths=[org_with_active_workers.parent])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org
            await app._connect_to_org(org_with_active_workers)
            await pilot.pause()

            # Switch to dashboard
            app.action_switch_tab("dashboard")
            await pilot.pause()

            # Get dashboard view and refresh
            dashboard = app.query_one("#dashboard-view", DashboardView)
            await dashboard.refresh_data()
            await pilot.pause()

            # Should show 3 workers
            worker_count_label = app.query_one("#worker-count", Label)
            assert get_label_text(worker_count_label) == "3"

            # Should show 3 active sessions (2 running + 1 idle)
            active_count_label = app.query_one("#active-count", Label)
            assert get_label_text(active_count_label) == "3"

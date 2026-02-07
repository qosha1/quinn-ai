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
from tests.conftest import create_test_org_db


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

        # Create database with production schema
        db_path = create_test_org_db(
            org_path,
            org_name="test-org-with-balances",
            status="running",
            include_ceo=True,
            ceo_name="Alice",
            include_board_channel=False,
        )

        conn = sqlite3.connect(str(db_path))

        # Schema already created by shared utility
        # Add additional test data
        now = datetime.now()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=30)

        # Add Engineering team
        conn.execute("INSERT INTO teams (id, name) VALUES ('team-eng', 'Engineering')")

        # Add developer worker (CEO already created)
        conn.execute("""
            INSERT INTO workers (id, name, role, team_id, manager_id, status, cost, created_at)
            VALUES ('worker-dev1', 'Bob', 'Developer', 'team-eng', 'worker-ceo', 'active', 50, ?)
        """, (now.isoformat(),))

        # Add developer session (CEO session already created if status='running')
        conn.execute("""
            INSERT INTO sessions (id, worker_id, provider, command, tmux_session_name, state, created_at)
            VALUES ('session-dev1', 'worker-dev1', 'claude_code', 'claude-code', 'org-test-org-dev1', 'idle', ?)
        """, (now.isoformat(),))

        # Add escalations channel
        conn.execute("INSERT INTO channels (id, name, type) VALUES ('ch-esc', 'escalations', 'topic')")

        # Add unread messages
        conn.execute("""
            INSERT INTO messages (id, channel_id, thread_id, parent_id, from_worker_id, content, priority, time_sensitivity, created_at)
            VALUES ('msg-1', 'ch-esc', NULL, NULL, 'worker-dev1', 'Need help with API design', 3, 'hours', ?)
        """, (now.isoformat(),))
        conn.execute("""
            INSERT INTO notification_beads (id, worker_id, message_id, channel_id, status, priority, created_at)
            VALUES ('nb-1', 'worker-ceo', 'msg-1', 'ch-esc', 'pending', 3, ?)
        """, (now.isoformat(),))

        # Create budget pool
        conn.execute("""
            INSERT INTO budget_pools (id, name, total_credits, period_start, period_end, created_at, updated_at)
            VALUES ('pool-1', 'Q1 Budget', 1000.00, ?, ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat(), now.isoformat()))

        # Create budget allocations
        conn.execute("""
            INSERT INTO budget_allocations (
                id, worker_id, pool_id, allocated_credits, spent_credits, reserved_credits,
                period_start, period_end, can_delegate, created_at, updated_at
            )
            VALUES ('alloc-ceo', 'worker-ceo', 'pool-1', 100.0, 0.0, 0.0, ?, ?, 0, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat(), now.isoformat()))
        conn.execute("""
            INSERT INTO budget_allocations (
                id, worker_id, pool_id, allocated_credits, spent_credits, reserved_credits,
                period_start, period_end, can_delegate, created_at, updated_at
            )
            VALUES ('alloc-dev1', 'worker-dev1', 'pool-1', 50.0, 0.0, 0.0, ?, ?, 0, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat(), now.isoformat()))

        # Create budget balances (correct state)
        conn.execute("""
            INSERT INTO budget_balances (
                allocation_id, worker_id, allocated, spent, reserved, available, delegated,
                period_start, period_end, updated_at
            )
            VALUES ('alloc-ceo', 'worker-ceo', 100.0, 25.50, 0.0, 74.50, 0.0, ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat()))
        conn.execute("""
            INSERT INTO budget_balances (
                allocation_id, worker_id, allocated, spent, reserved, available, delegated,
                period_start, period_end, updated_at
            )
            VALUES ('alloc-dev1', 'worker-dev1', 50.0, 12.75, 0.0, 37.25, 0.0, ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat()))

        # Add spend transactions for today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        conn.execute("""
            INSERT INTO budget_transactions (
                id, allocation_id, worker_id, type, amount, provider, model,
                description, created_at
            )
            VALUES ('tx-1', 'alloc-ceo', 'worker-ceo', 'spend', -5.25, 'anthropic', 'claude-3-opus',
                    'API call cost', ?)
        """, (today_start.isoformat(),))
        conn.execute("""
            INSERT INTO budget_transactions (
                id, allocation_id, worker_id, type, amount, provider, model,
                description, created_at
            )
            VALUES ('tx-2', 'alloc-dev1', 'worker-dev1', 'spend', -3.10, 'anthropic', 'claude-3-sonnet',
                    'API call cost', ?)
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

        db_path = create_test_org_db(org_path, status="running", include_ceo=True)
        conn = sqlite3.connect(str(db_path))

        # Insert test data
        now = datetime.now()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=30)

        # Create budget pool with allocations but NO balances (broken state)
        conn.execute("""
            INSERT INTO budget_pools (id, name, total_credits, period_start, period_end, created_at, updated_at)
            VALUES ('pool-1', 'Q1 Budget', 1000.00, ?, ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat(), now.isoformat()))

        conn.execute("""
            INSERT INTO budget_allocations (
                id, worker_id, pool_id, allocated_credits, spent_credits, reserved_credits,
                period_start, period_end, can_delegate, created_at, updated_at
            )
            VALUES ('alloc-ceo', 'worker-ceo', 'pool-1', 100.0, 0.0, 0.0, ?, ?, 0, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat(), now.isoformat()))

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

        db_path = create_test_org_db(org_path, status="running", include_ceo=True)
        conn = sqlite3.connect(str(db_path))

        # Insert test data with 3 active workers
        now = datetime.now()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=30)

        # Add Engineering team (Executive and CEO already created by shared utility)
        conn.execute("INSERT INTO teams (id, name) VALUES ('team-eng', 'Engineering')")

        # Add 2 developers (CEO already exists from shared utility)
        conn.execute("""
            INSERT INTO workers (id, name, role, team_id, manager_id, status, cost, created_at)
            VALUES ('worker-dev1', 'Bob', 'Developer', 'team-eng', 'worker-ceo', 'pending', 50, ?)
        """, (now.isoformat(),))
        conn.execute("""
            INSERT INTO workers (id, name, role, team_id, manager_id, status, cost, created_at)
            VALUES ('worker-dev2', 'Charlie', 'Developer', 'team-eng', 'worker-ceo', 'pending', 50, ?)
        """, (now.isoformat(),))

        # All 3 have active sessions (CEO session already created by shared utility)
        conn.execute("""
            INSERT INTO sessions (id, worker_id, provider, command, tmux_session_name, state)
            VALUES ('session-dev1', 'worker-dev1', 'claude_code', 'claude-code', 'org-test-org-dev1', 'running')
        """)
        conn.execute("""
            INSERT INTO sessions (id, worker_id, provider, command, tmux_session_name, state)
            VALUES ('session-dev2', 'worker-dev2', 'claude_code', 'claude-code', 'org-test-org-dev2', 'idle')
        """)

        # Create budget pool with balances
        conn.execute("""
            INSERT INTO budget_pools (id, name, total_credits, period_start, period_end, created_at, updated_at)
            VALUES ('pool-1', 'Q1 Budget', 1000.00, ?, ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat(), now.isoformat()))

        conn.execute("""
            INSERT INTO budget_allocations (
                id, worker_id, pool_id, allocated_credits, spent_credits, reserved_credits,
                period_start, period_end, can_delegate, created_at, updated_at
            )
            VALUES ('alloc-ceo', 'worker-ceo', 'pool-1', 100.0, 0.0, 0.0, ?, ?, 0, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat(), now.isoformat()))

        conn.execute("""
            INSERT INTO budget_balances (
                allocation_id, worker_id, allocated, spent, reserved, available, delegated,
                period_start, period_end, updated_at
            )
            VALUES ('alloc-ceo', 'worker-ceo', 100.0, 0.0, 0.0, 100.0, 0.0, ?, ?, ?)
        """, (period_start.isoformat(), period_end.isoformat(), now.isoformat()))

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

            db_path = create_test_org_db(org_path, status="running", include_ceo=True)

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

            db_path = create_test_org_db(org_path, status="initialized", include_ceo=False)

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

            # Verify CEO status is displayed (shows session state, not worker status)
            ceo_status_label = app.query_one("#ceo-status", Label)
            status_text = get_label_text(ceo_status_label)
            assert "Status:" in status_text
            # Session states: running, idle, stopped, crashed
            assert any(state in status_text for state in ["Idle", "Running", "Stopped", "Crashed"])

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

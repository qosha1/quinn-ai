"""
Test org restart with orphaned tmux sessions.

Reproduces bug where crashed sessions leave orphaned tmux sessions,
causing restart to fail with "session already exists" error.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from core.db import init_database
from core.org import Org
from core.sessions.tmux_spawner import TmuxSpawner
from core.sessions.spawner import SpawnerConfig
from shared.enums import OrgStatus


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
def initialized_org_obj(db):
    """Create an initialized org."""
    org = Org(db)
    org.init(ceo_name="Test CEO", initial_budget=1000.0)
    return org


class TestOrgRestartWithOrphanedSessions:
    """Test that org restart handles orphaned tmux sessions correctly."""

    def test_restart_with_orphaned_session_fails_without_cleanup(self, db, initialized_org_obj):
        """Verify that orphaned sessions cause restart to fail."""
        org = initialized_org_obj
        ceo = org.ceo

        tmux_session_name = f"qn-{ceo.id}"
        spawner = TmuxSpawner()

        try:
            # Create an orphaned session directly
            result = subprocess.run(
                ["tmux", "new-session", "-d", "-s", tmux_session_name, "bash"],
                capture_output=True,
            )
            assert result.returncode == 0, "Failed to create test orphaned session"
            assert spawner.is_alive(tmux_session_name), "Orphaned session should exist"

            # Trying to spawn another session with the same name should fail
            config = SpawnerConfig(
                command="bash",
                session_name=tmux_session_name,
                worker_id=ceo.id,
            )
            spawn_result = spawner.spawn(config)
            assert not spawn_result.success, "Spawn should fail when session already exists"
            assert spawn_result.error and "already exists" in spawn_result.error

        finally:
            try:
                spawner.stop(tmux_session_name, force=True)
            except Exception:
                pass
            db.close()

    def test_restart_with_orphaned_session_succeeds_with_cleanup(self, db, initialized_org_obj):
        """Verify that cleanup allows restart to succeed (the fix)."""
        org = initialized_org_obj
        ceo = org.ceo

        tmux_session_name = f"qn-{ceo.id}"
        spawner = TmuxSpawner()

        try:
            # Simulate orphaned session
            result = subprocess.run(
                ["tmux", "new-session", "-d", "-s", tmux_session_name, "bash"],
                capture_output=True,
            )
            assert result.returncode == 0
            assert spawner.is_alive(tmux_session_name)

            # Run startup cleanup to remove orphaned sessions
            from core.sessions import run_startup_cleanup

            cleanup_result = run_startup_cleanup(db)

            # Verify the orphaned session was killed
            assert cleanup_result.tmux_sessions_killed > 0, "Should have killed orphaned session"
            assert not spawner.is_alive(tmux_session_name), "Orphaned session should be gone"

            # Spawning a new session with the same name should now succeed
            config = SpawnerConfig(
                command="bash",
                session_name=tmux_session_name,
                worker_id=ceo.id,
            )
            spawn_result = spawner.spawn(config)
            assert spawn_result.success, f"Spawn should succeed after cleanup: {spawn_result.error}"
            assert spawner.is_alive(tmux_session_name), "New session should exist"

        finally:
            try:
                spawner.stop(tmux_session_name, force=True)
            except Exception:
                pass
            db.close()

    def test_startup_cleanup_is_idempotent(self, db, initialized_org_obj):
        """Verify that running cleanup multiple times is safe."""
        try:
            from core.sessions import run_startup_cleanup

            # Run cleanup when there are no orphans
            result1 = run_startup_cleanup(db)
            assert result1.tmux_sessions_killed == 0
            assert result1.db_records_updated == 0

            # Run again - should be the same
            result2 = run_startup_cleanup(db)
            assert result2.tmux_sessions_killed == 0
            assert result2.db_records_updated == 0

        finally:
            db.close()

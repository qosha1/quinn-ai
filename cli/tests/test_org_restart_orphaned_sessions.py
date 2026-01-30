"""
Test org restart with orphaned tmux sessions.

Reproduces bug where crashed sessions leave orphaned tmux sessions,
causing restart to fail with "session already exists" error.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from cli.core.db import init_database
from cli.core.org import Org
from cli.core.sessions.tmux_spawner import TmuxSpawner
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
        """Verify that orphaned sessions cause restart to fail (current bug)."""
        org = initialized_org_obj
        ceo = org.ceo

        try:

            # Simulate orphaned session - create a tmux session with the worker's name
            tmux_session_name = f"qn-{ceo.id}"
            spawner = TmuxSpawner()

            # Create an orphaned session directly
            result = subprocess.run(
                ["tmux", "new-session", "-d", "-s", tmux_session_name, "bash"],
                capture_output=True,
            )
            assert result.returncode == 0, "Failed to create test orphaned session"

            # Verify the orphaned session exists
            assert spawner.is_alive(tmux_session_name), "Orphaned session should exist"

            # Now try to start the org - this should fail with current code
            # because it will try to create a session with the same name
            from cli.core.session import SessionConfig
            from cli.core.sessions.registry import get_default_registry

            registry = get_default_registry()
            adapter = registry.get("claude_code")

            # Get org_path from db_path
            org_path = db.path.parent.parent

            session_config = SessionConfig(
                worker_id=ceo.id,
                provider="claude_code",
                command="claude",
                args="--dangerously-skip-permissions",
                working_dir=org_path / "storage" / "workers" / ceo.id,
                env_overrides={},
            )

            # This should fail because tmux session already exists
            with pytest.raises(Exception, match="Failed to spawn|returned non-zero exit status"):
                adapter.spawn(session_config)

        finally:
            # Cleanup: kill the orphaned session
            try:
                spawner.stop(tmux_session_name, force=True)
            except Exception:
                pass
            db.close()

    def test_restart_with_orphaned_session_succeeds_with_cleanup(self, db, initialized_org_obj):
        """Verify that cleanup allows restart to succeed (the fix)."""
        org = initialized_org_obj
        ceo = org.ceo

        try:

            # Simulate orphaned session
            tmux_session_name = f"qn-{ceo.id}"
            spawner = TmuxSpawner()

            result = subprocess.run(
                ["tmux", "new-session", "-d", "-s", tmux_session_name, "bash"],
                capture_output=True,
            )
            assert result.returncode == 0

            # Run startup cleanup to remove orphaned sessions
            from cli.core.sessions import run_startup_cleanup

            cleanup_result = run_startup_cleanup(db)

            # Verify the orphaned session was killed
            assert cleanup_result.tmux_sessions_killed > 0, "Should have killed orphaned session"
            assert not spawner.is_alive(tmux_session_name), "Orphaned session should be gone"

            # Now spawning should succeed
            from cli.core.session import SessionConfig
            from cli.core.sessions.registry import get_default_registry

            registry = get_default_registry()
            adapter = registry.get("claude_code")

            # Get org_path from db_path
            org_path = db.path.parent.parent

            session_config = SessionConfig(
                worker_id=ceo.id,
                provider="claude_code",
                command="claude",
                args="--dangerously-skip-permissions",
                working_dir=org_path / "storage" / "workers" / ceo.id,
                env_overrides={},
            )

            # This should now succeed
            adapter.spawn(session_config)

            # Verify session was created
            new_session_name = f"qn-{ceo.id}"
            assert spawner.is_alive(new_session_name), "New session should exist"

        finally:
            # Cleanup
            try:
                spawner.stop(f"qn-{ceo.id}", force=True)
            except Exception:
                pass
            db.close()

    def test_startup_cleanup_is_idempotent(self, db, initialized_org_obj):
        """Verify that running cleanup multiple times is safe."""
        try:
            from cli.core.sessions import run_startup_cleanup

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

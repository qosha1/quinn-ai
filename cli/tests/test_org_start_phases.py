"""
Tests for the 6-phase org start sequence (quinnai-3gqq).

Tests the CLI command phases:
- Phase 0 (Preflight): Validation
- Phase 1 (Cleanup): Orphaned session reconciliation
- Phase 2 (Transition): Org state changes
- Phase 3 (Onboarding): File system preparation
- Phase 4 (Session Spawn): CEO session creation
- Phase 5 (Kickstart): Initial prompt delivery
- Phase 6 (Readiness): Wait for session ready
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from core.db import init_database, open_database, get_org_db_path
from core.org import Org
from shared import InvalidOrgTransition, ConfigurationError
from shared.enums import OrgStatus, RuntimeStatus


@pytest.fixture
def temp_org_dir():
    """Create a temporary org directory with required structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / "live").mkdir(parents=True)
        (org_path / "config").mkdir(parents=True)
        (org_path / "storage" / "workers").mkdir(parents=True)
        (org_path / "storage" / "shared").mkdir(parents=True)
        (org_path / ".beads").mkdir(parents=True)
        yield org_path


@pytest.fixture
def test_db(temp_org_dir):
    """Create a test database."""
    db_path = temp_org_dir / "live" / "quinn.db"
    db = init_database(db_path)
    yield db
    db.close()


@pytest.fixture
def initialized_org(test_db, temp_org_dir):
    """Create an initialized org with CEO."""
    org = Org(test_db, temp_org_dir)
    org.init("TestCEO", "CEO")
    return org


# =============================================================================
# PHASE 0: PREFLIGHT VALIDATION TESTS
# =============================================================================

class TestPhase0Preflight:
    """Test Phase 0: Preflight validation."""

    def test_preflight_requires_org_database(self, temp_org_dir):
        """Preflight should fail if org database doesn't exist."""
        from commands.org.start import _validate_preflight

        # Remove the database
        db_path = temp_org_dir / "live" / "quinn.db"
        # Don't create db

        import click
        with pytest.raises(click.ClickException) as exc_info:
            _validate_preflight(temp_org_dir, skip_config_validation=True)

        assert "not initialized" in str(exc_info.value)

    def test_preflight_requires_directory_structure(self, temp_org_dir, test_db):
        """Preflight should fail if required directories are missing."""
        from commands.org.start import _validate_preflight

        # Remove a required directory
        (temp_org_dir / "storage" / "shared").rmdir()

        import click
        with pytest.raises(click.ClickException) as exc_info:
            _validate_preflight(temp_org_dir, skip_config_validation=True)

        assert "Missing required directory" in str(exc_info.value)

    def test_preflight_can_skip_config_validation(self, temp_org_dir, test_db):
        """Preflight should succeed with skip_config_validation=True."""
        from commands.org.start import _validate_preflight

        # No providers.yaml, but skip validation
        db = _validate_preflight(temp_org_dir, skip_config_validation=True)
        assert db is not None
        db.close()

    def test_determine_start_mode_first_start(self, initialized_org):
        """Determine start mode should return FIRST_START for initialized org."""
        from commands.org.start import _determine_start_mode, StartMode

        mode = _determine_start_mode(initialized_org)
        assert mode == StartMode.FIRST_START

    def test_determine_start_mode_resume(self, initialized_org):
        """Determine start mode should return RESUME for stopped org."""
        from commands.org.start import _determine_start_mode, StartMode

        initialized_org.start()
        initialized_org.stop()

        mode = _determine_start_mode(initialized_org)
        assert mode == StartMode.RESUME

    def test_determine_start_mode_already_running(self, initialized_org):
        """Determine start mode should return ALREADY_RUNNING for running org."""
        from commands.org.start import _determine_start_mode, StartMode

        initialized_org.start()

        mode = _determine_start_mode(initialized_org)
        assert mode == StartMode.ALREADY_RUNNING


# =============================================================================
# PHASE 1: CLEANUP TESTS
# =============================================================================

class TestPhase1Cleanup:
    """Test Phase 1: Orphaned session cleanup."""

    @patch('core.sessions.run_startup_cleanup')
    def test_cleanup_calls_startup_cleanup(self, mock_cleanup, test_db):
        """Cleanup should call run_startup_cleanup."""
        from commands.org.start import _cleanup_orphaned_sessions

        mock_result = Mock()
        mock_result.tmux_sessions_killed = 0
        mock_result.db_records_updated = 0
        mock_result.errors = []
        mock_cleanup.return_value = mock_result

        _cleanup_orphaned_sessions(test_db)

        mock_cleanup.assert_called_once_with(test_db)

    @patch('core.sessions.run_startup_cleanup')
    def test_cleanup_reports_killed_sessions(self, mock_cleanup, test_db, capsys):
        """Cleanup should report killed tmux sessions."""
        from commands.org.start import _cleanup_orphaned_sessions

        mock_result = Mock()
        mock_result.tmux_sessions_killed = 2
        mock_result.db_records_updated = 1
        mock_result.errors = []
        mock_cleanup.return_value = mock_result

        _cleanup_orphaned_sessions(test_db)

        captured = capsys.readouterr()
        assert "orphaned" in captured.out.lower()
        assert "2" in captured.out

    @patch('core.sessions.run_startup_cleanup')
    def test_cleanup_is_best_effort(self, mock_cleanup, test_db, capsys):
        """Cleanup failure should not raise, just warn."""
        from commands.org.start import _cleanup_orphaned_sessions

        mock_cleanup.side_effect = Exception("Cleanup failed")

        # Should not raise
        _cleanup_orphaned_sessions(test_db)

        captured = capsys.readouterr()
        assert "Warning" in captured.err or "warning" in captured.err.lower()


# =============================================================================
# PHASE 2: ORG STATE TRANSITION TESTS
# =============================================================================

class TestPhase2Transition:
    """Test Phase 2: Org state transition."""

    def test_transition_from_initialized_to_running(self, initialized_org, temp_org_dir):
        """Transition should move org from INITIALIZED to RUNNING."""
        from commands.org.start import _transition_org_state, StartMode

        old_status, new_status = _transition_org_state(
            initialized_org,
            StartMode.FIRST_START,
            temp_org_dir,
            initialized_org.db
        )

        assert old_status == OrgStatus.INITIALIZED.value
        assert new_status == OrgStatus.RUNNING.value
        assert initialized_org.status == OrgStatus.RUNNING.value

    def test_transition_from_stopped_to_running(self, initialized_org, temp_org_dir):
        """Transition should move org from STOPPED to RUNNING."""
        from commands.org.start import _transition_org_state, StartMode

        # First start then stop
        initialized_org.start()
        initialized_org.stop()

        old_status, new_status = _transition_org_state(
            initialized_org,
            StartMode.RESUME,
            temp_org_dir,
            initialized_org.db
        )

        assert old_status == OrgStatus.STOPPED.value
        assert new_status == OrgStatus.RUNNING.value

    def test_transition_activates_ceo(self, initialized_org, temp_org_dir):
        """Transition from INITIALIZED should activate CEO."""
        from commands.org.start import _transition_org_state, StartMode

        assert initialized_org.ceo.lifecycle_status == "pending"

        _transition_org_state(
            initialized_org,
            StartMode.FIRST_START,
            temp_org_dir,
            initialized_org.db
        )

        assert initialized_org.ceo.lifecycle_status == "active"

    def test_transition_handles_invalid_transition(self, initialized_org, temp_org_dir):
        """Transition should raise ClickException for invalid transitions."""
        from commands.org.start import _transition_org_state, StartMode
        import click

        initialized_org.start()

        with pytest.raises(click.ClickException) as exc_info:
            _transition_org_state(
                initialized_org,
                StartMode.FIRST_START,  # Wrong mode for running org
                temp_org_dir,
                initialized_org.db
            )

        assert "Cannot start" in str(exc_info.value)


# =============================================================================
# PHASE 3-5: ONBOARDING, SESSION SPAWN, KICKSTART TESTS
# =============================================================================

class TestPhase3Onboarding:
    """Test Phase 3: Onboarding preparation."""

    @patch('commands.org.start.prepare_worker_onboarding')
    @patch('commands.org.start.get_worker_env_vars')
    @patch('commands.org.start.get_default_registry')
    def test_onboarding_prepares_worker(
        self, mock_registry, mock_env_vars, mock_onboarding, initialized_org, temp_org_dir
    ):
        """Session spawn should call prepare_worker_onboarding."""
        from commands.org.start import _spawn_ceo_session_if_needed

        # Setup mocks
        mock_onboarding.return_value = Mock()
        mock_env_vars.return_value = {}
        mock_reg = MagicMock()
        mock_reg.has.return_value = True
        mock_registry.return_value = mock_reg

        # Mock the CEO spawn
        ceo = initialized_org.ceo
        ceo.spawn = Mock()
        ceo.set_registry = Mock()

        _spawn_ceo_session_if_needed(
            ceo, temp_org_dir, initialized_org.db,
            "claude_code", "claude", "--dangerously-skip-permissions", False
        )

        mock_onboarding.assert_called_once_with(initialized_org.db, ceo.id, temp_org_dir)


class TestPhase4SessionSpawn:
    """Test Phase 4: Session spawn."""

    @patch('commands.org.start.prepare_worker_onboarding')
    @patch('commands.org.start.get_worker_env_vars')
    @patch('commands.org.start.get_default_registry')
    def test_session_spawn_creates_session(
        self, mock_registry, mock_env_vars, mock_onboarding, initialized_org, temp_org_dir
    ):
        """Session spawn should call ceo.spawn() with config."""
        from commands.org.start import _spawn_ceo_session_if_needed

        # Setup mocks
        mock_onboarding.return_value = Mock()
        mock_env_vars.return_value = {"TEST": "value"}
        mock_reg = MagicMock()
        mock_reg.has.return_value = True
        mock_registry.return_value = mock_reg

        ceo = initialized_org.ceo
        ceo.spawn = Mock()
        ceo.set_registry = Mock()

        _spawn_ceo_session_if_needed(
            ceo, temp_org_dir, initialized_org.db,
            "claude_code", "claude", "--arg1 --arg2", False
        )

        ceo.spawn.assert_called_once()
        config = ceo.spawn.call_args[0][0]
        assert config.provider == "claude_code"
        assert config.command == "claude"
        assert "--arg1" in config.args

    @patch('commands.org.start.prepare_worker_onboarding')
    @patch('commands.org.start.get_worker_env_vars')
    @patch('commands.org.start.get_default_registry')
    def test_session_spawn_checks_provider_exists(
        self, mock_registry, mock_env_vars, mock_onboarding, initialized_org, temp_org_dir
    ):
        """Session spawn should raise if provider doesn't exist."""
        from commands.org.start import _spawn_ceo_session_if_needed
        from shared import SessionSpawnError

        # Setup mocks
        mock_onboarding.return_value = Mock()
        mock_env_vars.return_value = {}
        mock_reg = MagicMock()
        mock_reg.has.return_value = False  # Provider not found
        mock_reg.list_adapters.return_value = ["claude_code"]
        mock_registry.return_value = mock_reg

        ceo = initialized_org.ceo

        with pytest.raises(SessionSpawnError) as exc_info:
            _spawn_ceo_session_if_needed(
                ceo, temp_org_dir, initialized_org.db,
                "unknown_provider", "cmd", "", False
            )

        assert "unknown_provider" in str(exc_info.value)

    @patch('commands.org.start.prepare_worker_onboarding')
    @patch('commands.org.start.get_worker_env_vars')
    @patch('commands.org.start.get_default_registry')
    def test_session_spawn_skips_if_already_active(
        self, mock_registry, mock_env_vars, mock_onboarding, initialized_org, temp_org_dir, capsys
    ):
        """Session spawn should skip if CEO session already active."""
        from commands.org.start import _spawn_ceo_session_if_needed

        ceo = initialized_org.ceo
        # Mock is_session_active to return True
        with patch.object(type(ceo), 'is_session_active', new_callable=lambda: property(lambda self: True)):
            ceo.spawn = Mock()

            _spawn_ceo_session_if_needed(
                ceo, temp_org_dir, initialized_org.db,
                "claude_code", "claude", "", False
            )

            # Spawn should NOT be called
            ceo.spawn.assert_not_called()

            captured = capsys.readouterr()
            assert "already active" in captured.out


class TestPhase5Kickstart:
    """Test Phase 5: Initial prompt delivery."""

    @patch('subprocess.run')
    def test_kickstart_writes_initial_task_file(
        self, mock_subprocess, initialized_org, temp_org_dir
    ):
        """Kickstart should write INITIAL_TASK.md."""
        from commands.org.start import _send_initial_prompt_to_ceo

        worker_dir = temp_org_dir / "storage" / "workers" / "ceo"
        worker_dir.mkdir(parents=True, exist_ok=True)

        mock_subprocess.return_value = Mock()

        _send_initial_prompt_to_ceo(initialized_org.ceo, worker_dir)

        # Check file was created
        task_file = worker_dir / "INITIAL_TASK.md"
        assert task_file.exists()
        content = task_file.read_text()
        assert "CEO" in content or "BRIEFING" in content

    @patch('subprocess.run')
    def test_kickstart_sends_tmux_command(
        self, mock_subprocess, initialized_org, temp_org_dir
    ):
        """Kickstart should send command to tmux session."""
        from commands.org.start import _send_initial_prompt_to_ceo

        worker_dir = temp_org_dir / "storage" / "workers" / "ceo"
        worker_dir.mkdir(parents=True, exist_ok=True)

        mock_subprocess.return_value = Mock()

        _send_initial_prompt_to_ceo(initialized_org.ceo, worker_dir)

        # Should call tmux send-keys
        assert mock_subprocess.call_count >= 2  # send-keys + Enter

    @patch('subprocess.run')
    def test_kickstart_is_best_effort(
        self, mock_subprocess, initialized_org, temp_org_dir, capsys
    ):
        """Kickstart failure should not raise, just warn."""
        from commands.org.start import _send_initial_prompt_to_ceo

        worker_dir = temp_org_dir / "storage" / "workers" / "ceo"
        worker_dir.mkdir(parents=True, exist_ok=True)

        mock_subprocess.side_effect = Exception("tmux error")

        # Should not raise
        _send_initial_prompt_to_ceo(initialized_org.ceo, worker_dir)

        captured = capsys.readouterr()
        assert "Warning" in captured.err or "warning" in captured.err.lower()


# =============================================================================
# PHASE 6: READINESS TESTS
# =============================================================================

class TestPhase6Readiness:
    """Test Phase 6: Readiness verification."""

    def test_wait_for_ready_succeeds_on_running(self, initialized_org):
        """Wait should succeed when session reaches RUNNING."""
        from commands.org.start import _wait_for_ready

        ceo = initialized_org.ceo

        # Mock runtime_status to return RUNNING
        call_count = [0]
        original_getter = type(ceo).runtime_status.fget

        def mock_runtime_status(self):
            call_count[0] += 1
            if call_count[0] >= 2:
                return RuntimeStatus.RUNNING.value
            return RuntimeStatus.STARTING.value

        with patch.object(type(ceo), 'runtime_status', new_callable=lambda: property(mock_runtime_status)):
            # Should complete without error
            _wait_for_ready(ceo, timeout=5)

    def test_wait_for_ready_succeeds_on_idle(self, initialized_org):
        """Wait should succeed when session reaches IDLE."""
        from commands.org.start import _wait_for_ready

        ceo = initialized_org.ceo

        # Mock runtime_status to return IDLE
        with patch.object(type(ceo), 'runtime_status', new_callable=lambda: property(lambda self: RuntimeStatus.IDLE.value)):
            _wait_for_ready(ceo, timeout=5)
            # No error means success

    def test_wait_for_ready_times_out(self, initialized_org):
        """Wait should raise SessionStartTimeout on timeout."""
        from commands.org.start import _wait_for_ready
        from shared import SessionStartTimeout

        ceo = initialized_org.ceo

        # Mock runtime_status to stay at STARTING
        with patch.object(type(ceo), 'runtime_status', new_callable=lambda: property(lambda self: RuntimeStatus.STARTING.value)):
            with pytest.raises(SessionStartTimeout) as exc_info:
                _wait_for_ready(ceo, timeout=1)

            assert exc_info.value.worker_id == ceo.id


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestStartSequenceIntegration:
    """Integration tests for the full start sequence."""

    def test_org_state_after_successful_start(self, initialized_org, temp_org_dir):
        """After successful start phases 0-2, org should be RUNNING with active CEO."""
        from commands.org.start import (
            _validate_preflight,
            _cleanup_orphaned_sessions,
            _transition_org_state,
            _determine_start_mode,
        )

        # Phase 0: Preflight
        db = _validate_preflight(temp_org_dir, skip_config_validation=True)

        # Phase 1: Cleanup (mock to avoid tmux dependency)
        with patch('core.sessions.run_startup_cleanup') as mock_cleanup:
            mock_result = Mock()
            mock_result.tmux_sessions_killed = 0
            mock_result.db_records_updated = 0
            mock_result.errors = []
            mock_cleanup.return_value = mock_result
            _cleanup_orphaned_sessions(db)

        # Reload org from db
        org = Org.load(db)
        start_mode = _determine_start_mode(org)

        # Phase 2: Transition
        old_status, new_status = _transition_org_state(org, start_mode, temp_org_dir, db)

        # Verify final state
        assert org.status == OrgStatus.RUNNING.value
        assert org.ceo.lifecycle_status == "active"
        assert old_status == OrgStatus.INITIALIZED.value
        assert new_status == OrgStatus.RUNNING.value

        db.close()

    def test_session_spawn_failure_does_not_rollback_org(self, initialized_org, temp_org_dir):
        """Session spawn failure should NOT rollback org state (per design)."""
        from commands.org.start import (
            _transition_org_state,
            _spawn_ceo_session_if_needed,
            StartMode,
        )
        from shared import SessionSpawnError

        # First transition org
        _transition_org_state(initialized_org, StartMode.FIRST_START, temp_org_dir, initialized_org.db)
        assert initialized_org.status == OrgStatus.RUNNING.value

        # Mock spawn to fail
        with patch('commands.org.start.prepare_worker_onboarding') as mock_onboard:
            mock_onboard.return_value = Mock()
            with patch('commands.org.start.get_worker_env_vars') as mock_env:
                mock_env.return_value = {}
                with patch('commands.org.start.get_default_registry') as mock_reg:
                    mock_reg_instance = MagicMock()
                    mock_reg_instance.has.return_value = True
                    mock_reg.return_value = mock_reg_instance

                    ceo = initialized_org.ceo
                    ceo.spawn = Mock(side_effect=Exception("Spawn failed"))
                    ceo.set_registry = Mock()

                    with pytest.raises(SessionSpawnError):
                        _spawn_ceo_session_if_needed(
                            ceo, temp_org_dir, initialized_org.db,
                            "claude_code", "claude", "", False
                        )

        # Org should still be RUNNING (not rolled back)
        assert initialized_org.status == OrgStatus.RUNNING.value

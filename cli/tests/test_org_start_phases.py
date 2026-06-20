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

from cli.core.db import init_database, open_database, get_org_db_path
from cli.core.org import Org
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
        from cli.commands.org.start import _validate_preflight

        # Remove the database
        db_path = temp_org_dir / "live" / "quinn.db"
        # Don't create db

        import click
        with pytest.raises(click.ClickException) as exc_info:
            _validate_preflight(temp_org_dir, skip_config_validation=True)

        assert "not initialized" in str(exc_info.value)

    def test_preflight_requires_directory_structure(self, temp_org_dir, test_db):
        """Preflight should fail if required directories are missing."""
        from cli.commands.org.start import _validate_preflight

        # Remove a required directory
        (temp_org_dir / "storage" / "shared").rmdir()

        import click
        with pytest.raises(click.ClickException) as exc_info:
            _validate_preflight(temp_org_dir, skip_config_validation=True)

        assert "Missing required directory" in str(exc_info.value)

    def test_preflight_can_skip_config_validation(self, temp_org_dir, test_db):
        """Preflight should succeed with skip_config_validation=True."""
        from cli.commands.org.start import _validate_preflight

        # No providers.yaml, but skip validation
        db = _validate_preflight(temp_org_dir, skip_config_validation=True)
        assert db is not None
        db.close()

    def test_determine_start_mode_first_start(self, initialized_org):
        """Determine start mode should return FIRST_START for initialized org."""
        from cli.commands.org.start import _determine_start_mode, StartMode

        mode = _determine_start_mode(initialized_org)
        assert mode == StartMode.FIRST_START

    def test_determine_start_mode_resume(self, initialized_org):
        """Determine start mode should return RESUME for stopped org."""
        from cli.commands.org.start import _determine_start_mode, StartMode

        initialized_org.start()
        initialized_org.stop()

        mode = _determine_start_mode(initialized_org)
        assert mode == StartMode.RESUME

    def test_determine_start_mode_already_running(self, initialized_org):
        """Determine start mode should return ALREADY_RUNNING for running org."""
        from cli.commands.org.start import _determine_start_mode, StartMode

        initialized_org.start()

        mode = _determine_start_mode(initialized_org)
        assert mode == StartMode.ALREADY_RUNNING


# =============================================================================
# PHASE 1: CLEANUP TESTS
# =============================================================================

class TestPhase1Cleanup:
    """Test Phase 1: Orphaned session cleanup."""

    @patch('cli.core.sessions.run_startup_cleanup')
    def test_cleanup_calls_startup_cleanup(self, mock_cleanup, test_db):
        """Cleanup should call run_startup_cleanup."""
        from cli.commands.org.start import _cleanup_orphaned_sessions

        mock_result = Mock()
        mock_result.tmux_sessions_killed = 0
        mock_result.db_records_updated = 0
        mock_result.errors = []
        mock_cleanup.return_value = mock_result

        _cleanup_orphaned_sessions(test_db)

        mock_cleanup.assert_called_once_with(test_db)

    @patch('cli.core.sessions.run_startup_cleanup')
    def test_cleanup_reports_killed_sessions(self, mock_cleanup, test_db, capsys):
        """Cleanup should report killed tmux sessions."""
        from cli.commands.org.start import _cleanup_orphaned_sessions

        mock_result = Mock()
        mock_result.tmux_sessions_killed = 2
        mock_result.db_records_updated = 1
        mock_result.errors = []
        mock_cleanup.return_value = mock_result

        _cleanup_orphaned_sessions(test_db)

        captured = capsys.readouterr()
        assert "orphaned" in captured.out.lower()
        assert "2" in captured.out

    @patch('cli.core.sessions.run_startup_cleanup')
    def test_cleanup_is_best_effort(self, mock_cleanup, test_db, capsys):
        """Cleanup failure should not raise, just warn."""
        from cli.commands.org.start import _cleanup_orphaned_sessions

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
        from cli.commands.org.start import _transition_org_state, StartMode

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
        from cli.commands.org.start import _transition_org_state, StartMode

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
        from cli.commands.org.start import _transition_org_state, StartMode

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
        from cli.commands.org.start import _transition_org_state, StartMode
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

    @patch('cli.core.org_start_controller.prepare_worker_onboarding')
    @patch('cli.core.org_start_controller.get_worker_env_vars')
    @patch('cli.core.org_start_controller.get_default_registry')
    def test_onboarding_prepares_worker(
        self, mock_registry, mock_env_vars, mock_onboarding, initialized_org, temp_org_dir
    ):
        """Session spawn should call prepare_worker_onboarding."""
        from cli.commands.org.start import _spawn_ceo_session_if_needed

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

    @patch('cli.core.org_start_controller.prepare_worker_onboarding')
    @patch('cli.core.org_start_controller.get_worker_env_vars')
    @patch('cli.core.org_start_controller.get_default_registry')
    def test_session_spawn_creates_session(
        self, mock_registry, mock_env_vars, mock_onboarding, initialized_org, temp_org_dir
    ):
        """Session spawn should call ceo.spawn() with config."""
        from cli.commands.org.start import _spawn_ceo_session_if_needed

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

    @patch('cli.core.org_start_controller.prepare_worker_onboarding')
    @patch('cli.core.org_start_controller.get_worker_env_vars')
    @patch('cli.core.org_start_controller.get_default_registry')
    def test_session_spawn_checks_provider_exists(
        self, mock_registry, mock_env_vars, mock_onboarding, initialized_org, temp_org_dir
    ):
        """Session spawn should raise if provider doesn't exist."""
        from cli.commands.org.start import _spawn_ceo_session_if_needed
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

    @patch('cli.core.org_start_controller.prepare_worker_onboarding')
    @patch('cli.core.org_start_controller.get_worker_env_vars')
    @patch('cli.core.org_start_controller.get_default_registry')
    def test_session_spawn_skips_if_already_active(
        self, mock_registry, mock_env_vars, mock_onboarding, initialized_org, temp_org_dir, capsys
    ):
        """Session spawn should skip if CEO session already active."""
        from cli.commands.org.start import _spawn_ceo_session_if_needed

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
        from cli.commands.org.start import _send_initial_prompt_to_ceo

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
        from cli.commands.org.start import _send_initial_prompt_to_ceo

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
        from cli.commands.org.start import _send_initial_prompt_to_ceo

        worker_dir = temp_org_dir / "storage" / "workers" / "ceo"
        worker_dir.mkdir(parents=True, exist_ok=True)

        mock_subprocess.side_effect = Exception("tmux error")

        # Should not raise
        _send_initial_prompt_to_ceo(initialized_org.ceo, worker_dir)

        captured = capsys.readouterr()
        assert "Warning" in captured.err or "warning" in captured.err.lower()

    @patch('subprocess.run')
    def test_kickstart_initial_task_is_first_person_not_injection_shaped(
        self, mock_subprocess, initialized_org, temp_org_dir
    ):
        """Regression for quinn-ai-hdd8 AND quinn-ai-58rw — two opposite
        failure modes that must both be avoided.

        - Too 3rd-person ("You are {self_intro}. You've just been
          onboarded.") => the CEO read the cat'd file as documentation
          about a DIFFERENT worker and refused to act (hdd8).
        - Too emphatic ("=== EXECUTE THIS NOW ===", "You ARE the worker
          described", "Do not summarize", "Execute now") => security-
          conscious workers flag it as prompt injection / authority-
          laundering and refuse (58rw, caught live in canary 12).

        The balance: the file must read as the reader's OWN onboarding
        brief and lead into a concrete first action, WITHOUT injection-
        shaped framing.
        """
        from cli.commands.org.start import _send_initial_prompt_to_ceo

        worker_dir = temp_org_dir / "storage" / "workers" / "ceo"
        worker_dir.mkdir(parents=True, exist_ok=True)

        mock_subprocess.return_value = Mock()

        _send_initial_prompt_to_ceo(initialized_org.ceo, worker_dir)

        content = (worker_dir / "INITIAL_TASK.md").read_text()
        low = content.lower()
        # Whitespace-flattened view so phrase checks survive line wrapping.
        flat = " ".join(content.split()).lower()

        # First-person: clearly the reader's OWN brief (counters hdd8
        # 3rd-person dissociation).
        assert "you've just been onboarded" in flat, (
            "INITIAL_TASK.md must address the reader as the worker who was "
            "just onboarded, not describe a third party (quinn-ai-hdd8)."
        )
        assert "this is your onboarding brief" in flat, (
            "INITIAL_TASK.md must frame itself as the reader's own "
            "onboarding brief (quinn-ai-hdd8)."
        )

        # Leads into a concrete first action, not a passive document.
        assert "msgr inbox" in content, (
            "INITIAL_TASK.md must lead into a concrete first action."
        )

        # NOT injection-shaped (counters 58rw — these phrases make aligned
        # models refuse).
        for banned in (
            "=== execute this now",
            "you are the worker described",
            "do not summarize",
            "begin executing immediately",
            "execute now",
        ):
            assert banned not in low, (
                f"INITIAL_TASK.md must not use injection-shaped framing "
                f"{banned!r} — aligned workers refuse it (quinn-ai-58rw)."
            )


class TestPhase5VerificationContentAware:
    """Phase 5 verification must check pane CONTENT, not just diff (quinn-ai-moho).

    Original verification: pane_after != pane_before → success. False-positive
    when claude TUI itself redraws between pane_before and pane_after (cursor
    blinks, status bar updates, post-boot rendering finishing). Phase 5 then
    reports 'delivered' even though the cat command never landed in claude's
    input. CEO sits idle while qn claims success.
    """

    @patch("cli.core.org_start_controller._tmux_send_keys_with_retry")
    @patch("cli.core.org_start_controller._wait_for_pane_ready")
    @patch("cli.core.org_start_controller._capture_pane")
    @patch("cli.core.org_start_controller.time.sleep")  # skip timing waits
    def test_warns_when_pane_diff_but_no_cat_evidence(
        self,
        mock_sleep,
        mock_capture,
        mock_ready,
        mock_send_keys,
        initialized_org,
        temp_org_dir,
        capsys,
    ):
        """Pane changes but contains no cat-command evidence → must warn, not succeed."""
        from cli.core.org_start_controller import _send_initial_prompt_to_ceo

        worker_dir = temp_org_dir / "storage" / "workers" / "ceo"
        worker_dir.mkdir(parents=True, exist_ok=True)

        mock_ready.return_value = True
        mock_send_keys.return_value = True
        # Distinct panes (diff is non-zero) but neither contains cat or
        # any claude processing indicator — keystrokes did not land.
        # Verification polls multiple times; cycle through the two states.
        from itertools import cycle
        mock_capture.side_effect = cycle([
            "bash-3.2$ \n❯ ",                              # pane_before
            "bash-3.2$ \n❯ \n  status bar redraw flicker",  # pane_after polls
        ])

        _send_initial_prompt_to_ceo(initialized_org.ceo, worker_dir)

        captured = capsys.readouterr()
        # Must NOT print the success banner — verification was a false positive.
        assert "Initial task instructions delivered" not in captured.out, (
            "Verification reported delivered/processing but the pane shows "
            "no evidence the cat command landed — that's the moho bug."
        )
        # Must surface the warning so the operator knows to intervene.
        assert "no pane activity" in captured.err.lower() or "may not have received" in captured.err.lower(), (
            f"Expected a warning about delivery uncertainty. Got stderr:\n{captured.err}"
        )

    @patch("cli.core.org_start_controller._tmux_send_keys_with_retry")
    @patch("cli.core.org_start_controller._wait_for_pane_ready")
    @patch("cli.core.org_start_controller._capture_pane")
    @patch("cli.core.org_start_controller.time.sleep")
    def test_succeeds_when_cat_command_visible_in_pane(
        self,
        mock_sleep,
        mock_capture,
        mock_ready,
        mock_send_keys,
        initialized_org,
        temp_org_dir,
        capsys,
    ):
        """When pane_after contains the cat command, delivery succeeded."""
        from cli.core.org_start_controller import _send_initial_prompt_to_ceo

        worker_dir = temp_org_dir / "storage" / "workers" / "ceo"
        worker_dir.mkdir(parents=True, exist_ok=True)

        mock_ready.return_value = True
        mock_send_keys.return_value = True
        from itertools import cycle
        mock_capture.side_effect = cycle([
            "❯ ",
            f"❯ cat {worker_dir / 'INITIAL_TASK.md'}\n⏺ Reading file…",
        ])

        _send_initial_prompt_to_ceo(initialized_org.ceo, worker_dir)

        captured = capsys.readouterr()
        assert "Initial task instructions delivered" in captured.out


# =============================================================================
# PHASE 6: READINESS TESTS
# =============================================================================

class TestPhase6Readiness:
    """Test Phase 6: Readiness verification."""

    def test_wait_for_ready_succeeds_on_running(self, initialized_org):
        """Wait should succeed when session reaches RUNNING."""
        from cli.commands.org.start import _wait_for_ready

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
        from cli.commands.org.start import _wait_for_ready

        ceo = initialized_org.ceo

        # Mock runtime_status to return IDLE
        with patch.object(type(ceo), 'runtime_status', new_callable=lambda: property(lambda self: RuntimeStatus.IDLE.value)):
            _wait_for_ready(ceo, timeout=5)
            # No error means success

    def test_wait_for_ready_times_out(self, initialized_org):
        """Wait should raise SessionStartTimeout on timeout."""
        from cli.commands.org.start import _wait_for_ready
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
        from cli.commands.org.start import (
            _validate_preflight,
            _cleanup_orphaned_sessions,
            _transition_org_state,
            _determine_start_mode,
        )

        # Phase 0: Preflight
        db = _validate_preflight(temp_org_dir, skip_config_validation=True)

        # Phase 1: Cleanup (mock to avoid tmux dependency)
        with patch('cli.core.sessions.run_startup_cleanup') as mock_cleanup:
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
        from cli.commands.org.start import (
            _transition_org_state,
            _spawn_ceo_session_if_needed,
            StartMode,
        )
        from shared import SessionSpawnError

        # First transition org
        _transition_org_state(initialized_org, StartMode.FIRST_START, temp_org_dir, initialized_org.db)
        assert initialized_org.status == OrgStatus.RUNNING.value

        # Mock spawn to fail
        with patch('cli.core.org_start_controller.prepare_worker_onboarding') as mock_onboard:
            mock_onboard.return_value = Mock()
            with patch('cli.core.org_start_controller.get_worker_env_vars') as mock_env:
                mock_env.return_value = {}
                with patch('cli.core.org_start_controller.get_default_registry') as mock_reg:
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


class TestWaitForPaneReady:
    """qim4: _wait_for_pane_ready must wait for the actual TUI prompt cursor,
    not just any pane content.

    The bug: the prior heuristic was 'has ❯ OR len(pane.strip()) > 200'.
    The 200-char fallback matched bash echoing the long claude-launch
    command + dozens of blank lines BEFORE Claude Code's TUI rendered its
    prompt. Phase 5 then send-keys'd 'cat INITIAL_TASK.md' into a
    not-yet-receptive TUI and the keystrokes vanished — CEO sat idle
    forever with no directive (e.g. canary 09 every run on 2026-04-28).
    """

    @patch('cli.core.org_start_controller._capture_pane')
    def test_does_not_match_pre_tui_bash_output(self, mock_capture):
        """qim4 root cause: 311-char bash output without ❯ MUST NOT count
        as ready. This is the exact pane content from canary 09's failed
        kickstart instrumentation:
          'bash-3.2$ env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN
           claude --dangerously-skip-permissions\n\n\n\n\n\n\n\n\n\n...'
        """
        from cli.core.org_start_controller import _wait_for_pane_ready

        # Same content the diagnostic captured: bash command + many blank
        # lines, no ❯, length > 200.
        pre_tui = (
            "The default interactive shell is now zsh.\n"
            "To update your account to use zsh, please run `chsh -s /bin/zsh`.\n"
            "For more details, please visit https://support.apple.com/kb/HT208050.\n"
            "bash-3.2$ env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN claude --dangerously-skip-permissions\n"
            + ("\n" * 36)
        )
        assert len(pre_tui.strip()) > 200  # would have tripped the old heuristic
        assert "❯" not in pre_tui          # but TUI not yet rendered

        mock_capture.return_value = pre_tui

        # Tight timeout so the test fails fast if the heuristic regresses.
        result = _wait_for_pane_ready(
            "fake-session", timeout=0.5, poll_interval=0.1
        )
        assert result is False, (
            "pre-TUI bash output should NOT count as ready"
        )

    @patch('cli.core.org_start_controller._capture_pane')
    def test_matches_real_claude_code_prompt(self, mock_capture):
        """Once the Claude Code TUI renders its ❯ cursor, ready=True."""
        from cli.core.org_start_controller import _wait_for_pane_ready

        rendered = (
            "bash-3.2$ claude\n"
            " ▐▛███▜▌   Claude Code v2.1.122\n"
            "▝▜█████▛▘  Opus 4.7 (1M context)\n"
            "────────────────────\n"
            "❯ \n"
            "────────────────────\n"
        )
        mock_capture.return_value = rendered

        assert _wait_for_pane_ready(
            "fake-session", timeout=2.0, poll_interval=0.05
        ) is True

    @patch('cli.core.org_start_controller._capture_pane')
    def test_returns_false_on_timeout_when_tui_never_renders(self, mock_capture):
        """If the prompt never appears within timeout, return False."""
        from cli.core.org_start_controller import _wait_for_pane_ready

        mock_capture.return_value = "bash-3.2$ \n"  # no claude TUI ever

        assert _wait_for_pane_ready(
            "fake-session", timeout=0.3, poll_interval=0.1
        ) is False

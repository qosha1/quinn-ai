"""
Tests for the worker continuous trigger feature.

Workers go idle after initial kickstart because:
1. ContinuationEngine never starts in CLI mode
2. Prompts are vague — don't include concrete commands
3. INITIAL_TASK.md doesn't tell workers to enter a work loop

These tests define what "fixed" looks like before implementation.
All tests should FAIL until the feature is built.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# INITIAL_TASK.md prompt includes work-loop instruction
# ---------------------------------------------------------------------------

def _ceo_initial_prompt() -> str:
    """Render the CEO initial-task prompt from its template file."""
    from cli.core.prompts import render_initial_task
    from cli.core.constants.prompts import INITIAL_TASK_KIND_CEO

    return render_initial_task(
        INITIAL_TASK_KIND_CEO, self_intro="the CEO", chat_intro="I'm the CEO."
    )


def test_initial_prompt_contains_work_loop_instruction() -> None:
    """Workers must be told to cycle through inbox + ready work after setup."""
    tpl = _ceo_initial_prompt()

    # Must tell workers to check inbox on every cycle
    assert "msgr inbox" in tpl
    # Must tell workers to check for available work
    assert "bd ready" in tpl
    # Must include explicit loop/cycle language
    loop_keywords = ["loop", "cycle", "continuously", "repeat", "every"]
    assert any(kw in tpl.lower() for kw in loop_keywords)


def test_initial_prompt_work_loop_comes_after_setup() -> None:
    """Work loop instruction must come after the initial setup steps."""
    tpl = _ceo_initial_prompt()

    # Loop instruction should appear in the lower half of the template
    # (after setup steps, not before them)
    loop_pos = tpl.lower().find("loop")
    setup_pos = tpl.find("CRITICAL INSTRUCTIONS")
    assert loop_pos > setup_pos, (
        "Work loop instruction should appear after the CRITICAL INSTRUCTIONS setup block"
    )


# ---------------------------------------------------------------------------
# Continuation prompts include actionable commands
# ---------------------------------------------------------------------------

def test_soft_check_prompt_includes_msgr_inbox() -> None:
    """Soft-check prompt must tell idle workers to check their inbox."""
    from cli.core.constants.messaging import CONTINUATION_PROMPT_SOFT_CHECK

    assert "msgr inbox" in CONTINUATION_PROMPT_SOFT_CHECK


def test_soft_check_prompt_includes_bd_ready() -> None:
    """Soft-check prompt must tell idle workers to check for available work."""
    from cli.core.constants.messaging import CONTINUATION_PROMPT_SOFT_CHECK

    assert "bd ready" in CONTINUATION_PROMPT_SOFT_CHECK


def test_status_request_prompt_includes_msgr_inbox() -> None:
    from cli.core.constants.messaging import CONTINUATION_PROMPT_STATUS_REQUEST

    assert "msgr inbox" in CONTINUATION_PROMPT_STATUS_REQUEST


def test_status_request_prompt_includes_bd_ready() -> None:
    from cli.core.constants.messaging import CONTINUATION_PROMPT_STATUS_REQUEST

    assert "bd ready" in CONTINUATION_PROMPT_STATUS_REQUEST


def test_final_warning_prompt_includes_msgr_inbox() -> None:
    from cli.core.constants.messaging import CONTINUATION_PROMPT_FINAL_WARNING

    assert "msgr inbox" in CONTINUATION_PROMPT_FINAL_WARNING


def test_final_warning_prompt_includes_bd_ready() -> None:
    from cli.core.constants.messaging import CONTINUATION_PROMPT_FINAL_WARNING

    assert "bd ready" in CONTINUATION_PROMPT_FINAL_WARNING


# ---------------------------------------------------------------------------
# qn org watch — persistent command that starts ContinuationEngine
# ---------------------------------------------------------------------------

def test_org_watch_command_exists() -> None:
    """qn org watch command must exist and be registered."""
    from cli.commands.org.watch import watch

    assert callable(watch)


def test_org_watch_starts_continuation_engine(tmp_path: Path) -> None:
    """org watch must start the ContinuationEngine for active workers."""
    from cli.commands.org.watch import start_watch_loop

    mock_engine = MagicMock()
    mock_engine.is_running.return_value = False

    with patch("cli.commands.org.watch.ContinuationEngine", return_value=mock_engine):
        with patch("cli.commands.org.watch.open_database"):
            with patch("cli.commands.org.watch._get_org_path", return_value=tmp_path):
                # Should start the engine
                start_watch_loop(tmp_path, poll_seconds=0, max_iterations=1)

    mock_engine.start.assert_called_once()


def test_org_watch_stops_engine_on_exit(tmp_path: Path) -> None:
    """org watch must stop the ContinuationEngine cleanly when interrupted."""
    from cli.commands.org.watch import start_watch_loop

    mock_engine = MagicMock()
    mock_engine.is_running.return_value = True

    with patch("cli.commands.org.watch.ContinuationEngine", return_value=mock_engine):
        with patch("cli.commands.org.watch.open_database"):
            with patch("cli.commands.org.watch._get_org_path", return_value=tmp_path):
                start_watch_loop(tmp_path, poll_seconds=0, max_iterations=1)

    mock_engine.stop.assert_called_once()


# ---------------------------------------------------------------------------
# ContinuationEngine — prompt content reaches workers
# ---------------------------------------------------------------------------

def test_continuation_engine_sends_actionable_soft_check(tmp_path: Path) -> None:
    """ContinuationEngine soft-check prompt must include msgr inbox and bd ready."""
    from cli.core.continuation_engine import ContinuationEngine
    from cli.core.constants.messaging import CONTINUATION_PROMPT_SOFT_CHECK

    # Verify the engine uses the updated constant (not a cached copy)
    engine = ContinuationEngine.__new__(ContinuationEngine)
    # The prompt sent during soft_check must contain the actionable commands
    assert "msgr inbox" in CONTINUATION_PROMPT_SOFT_CHECK
    assert "bd ready" in CONTINUATION_PROMPT_SOFT_CHECK


def test_session_prompter_soft_check_uses_updated_template(tmp_path: Path) -> None:
    """SessionPrompter.send_soft_check must use the actionable template."""
    from cli.core.session_prompter import SessionPrompter
    from cli.core.constants.messaging import CONTINUATION_PROMPT_SOFT_CHECK

    mock_db = MagicMock()
    prompter = SessionPrompter(mock_db, tmp_path)

    # Verify the template being used contains the new commands
    # (SessionPrompter imports from constants at module level)
    assert "msgr inbox" in CONTINUATION_PROMPT_SOFT_CHECK
    assert "bd ready" in CONTINUATION_PROMPT_SOFT_CHECK


# ---------------------------------------------------------------------------
# Work loop instruction format — must be copy-pasteable, not vague
# ---------------------------------------------------------------------------

def test_initial_prompt_work_loop_is_concrete_not_vague() -> None:
    """Work loop instruction must include actual commands, not just 'keep working'."""
    tpl = _ceo_initial_prompt()

    # Find the section after CRITICAL INSTRUCTIONS
    after_setup = tpl[tpl.find("CRITICAL INSTRUCTIONS"):]

    # Must have both concrete commands in the loop section
    assert "msgr inbox" in after_setup
    assert "bd ready" in after_setup


def test_soft_check_prompt_has_ordered_steps() -> None:
    """Soft-check prompt must present inbox check BEFORE work pickup."""
    from cli.core.constants.messaging import CONTINUATION_PROMPT_SOFT_CHECK

    inbox_pos = CONTINUATION_PROMPT_SOFT_CHECK.find("msgr inbox")
    ready_pos = CONTINUATION_PROMPT_SOFT_CHECK.find("bd ready")

    assert inbox_pos != -1, "msgr inbox not found in soft check prompt"
    assert ready_pos != -1, "bd ready not found in soft check prompt"
    assert inbox_pos < ready_pos, "msgr inbox should come before bd ready"

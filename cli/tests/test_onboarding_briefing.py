"""Tests for enhanced briefing with first actions (GAP 3 fix)."""

import tempfile
from pathlib import Path

import pytest

from core.onboarding import (
    _generate_first_actions,
    _get_escalation_timeout,
    prepare_worker_onboarding,
)
from core.db import init_database
from core.queries.okr import create_okr, KeyResult
from core.constants import (
    DEFAULT_ESCALATION_TIMEOUT_CEO,
    DEFAULT_ESCALATION_TIMEOUT_MANAGER,
    DEFAULT_ESCALATION_TIMEOUT_WORKER,
)


@pytest.fixture
def temp_org_dir():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / "config").mkdir(parents=True)
        (org_path / "config" / "templates").mkdir(parents=True)
        (org_path / "storage" / "workers").mkdir(parents=True)
        (org_path / "storage" / "shared").mkdir(parents=True)
        yield org_path


@pytest.fixture
def test_db():
    """Create a test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    db = init_database(db_path)
    yield db
    db.close()
    db_path.unlink()


def test_generate_first_actions_ceo_with_okrs():
    """Test first actions for CEO with OKRs."""
    actions = _generate_first_actions(
        worker_role="CEO",
        worker_id="ceo-123",
        is_ceo=True,
        is_manager=False,
        has_okrs=True,
        manager_name=None,
    )

    assert len(actions) > 0
    # Should include OKR review
    assert any("OKR" in action or "okr" in action for action in actions)
    # Should include checking work
    assert any("bd ready" in action for action in actions)
    # Should be specific actions, not generic
    assert any("Review" in action or "Check" in action or "Start" in action for action in actions)


def test_generate_first_actions_ceo_without_okrs():
    """Test first actions for CEO without OKRs."""
    actions = _generate_first_actions(
        worker_role="CEO",
        worker_id="ceo-123",
        is_ceo=True,
        is_manager=False,
        has_okrs=False,
        manager_name=None,
    )

    assert len(actions) > 0
    # Should include creating OKRs
    assert any("Create" in action and ("OKR" in action or "okr" in action) for action in actions)
    # Should guide them to create key results
    assert any("key result" in action.lower() for action in actions)
    # Should mention hiring
    assert any("hire" in action.lower() or "Hire" in action for action in actions)


def test_generate_first_actions_manager_with_okrs():
    """Test first actions for manager with OKRs."""
    actions = _generate_first_actions(
        worker_role="Director",
        worker_id="dir-123",
        is_ceo=False,
        is_manager=True,
        has_okrs=True,
        manager_name="Alice (CEO)",
    )

    assert len(actions) > 0
    # Should include reviewing OKRs
    assert any("OKR" in action or "okr" in action for action in actions)
    # Should mention breaking down work
    assert any("task" in action.lower() for action in actions)
    # Should mention team
    assert any("team" in action.lower() for action in actions)
    # Should reference manager
    assert any("Alice" in action for action in actions)


def test_generate_first_actions_manager_without_okrs():
    """Test first actions for manager without OKRs."""
    actions = _generate_first_actions(
        worker_role="Director",
        worker_id="dir-123",
        is_ceo=False,
        is_manager=True,
        has_okrs=False,
        manager_name="Bob (CEO)",
    )

    assert len(actions) > 0
    # Should mention getting OKRs from manager
    assert any("Bob" in action and ("OKR" in action or "okr" in action) for action in actions)
    # Should suggest creating a plan
    assert any("plan" in action.lower() for action in actions)


def test_generate_first_actions_regular_worker():
    """Test first actions for regular worker."""
    actions = _generate_first_actions(
        worker_role="Engineer",
        worker_id="eng-123",
        is_ceo=False,
        is_manager=False,
        has_okrs=True,
        manager_name="Charlie (Director)",
    )

    assert len(actions) > 0
    # Should include checking assigned work
    assert any("bd ready" in action for action in actions)
    # Should mention syncing with manager
    assert any("Charlie" in action for action in actions)
    # Should mention architecture docs
    assert any("CLAUDE.md" in action for action in actions)


def test_get_escalation_timeout_ceo():
    """Test escalation timeout for CEO."""
    timeout = _get_escalation_timeout("CEO", is_ceo=True, is_manager=False)
    assert timeout == DEFAULT_ESCALATION_TIMEOUT_CEO
    assert timeout > DEFAULT_ESCALATION_TIMEOUT_MANAGER  # CEO gets more time


def test_get_escalation_timeout_manager():
    """Test escalation timeout for manager."""
    timeout = _get_escalation_timeout("Director", is_ceo=False, is_manager=True)
    assert timeout == DEFAULT_ESCALATION_TIMEOUT_MANAGER
    assert timeout > DEFAULT_ESCALATION_TIMEOUT_WORKER  # Manager gets more time than worker
    assert timeout < DEFAULT_ESCALATION_TIMEOUT_CEO  # But less than CEO


def test_get_escalation_timeout_worker():
    """Test escalation timeout for regular worker."""
    timeout = _get_escalation_timeout("Engineer", is_ceo=False, is_manager=False)
    assert timeout == DEFAULT_ESCALATION_TIMEOUT_WORKER
    assert timeout < DEFAULT_ESCALATION_TIMEOUT_MANAGER  # Worker has shortest timeout


def test_first_actions_are_actionable():
    """Test that first actions are specific and actionable, not generic."""
    # CEO with OKRs
    ceo_actions = _generate_first_actions(
        worker_role="CEO",
        worker_id="ceo",
        is_ceo=True,
        is_manager=False,
        has_okrs=True,
        manager_name=None,
    )

    # Each action should contain a verb and specific guidance
    for action in ceo_actions:
        # Should have action verbs
        has_verb = any(verb in action for verb in [
            "Review", "Check", "Start", "Create", "Document",
            "Run", "Pick", "Add", "Break", "Sync", "Introduce", "Post"
        ])
        assert has_verb, f"Action lacks action verb: {action}"

        # Should not be too generic
        assert len(action) > 20, f"Action too generic: {action}"

        # Should contain specific commands or guidance
        has_specifics = (
            "`" in action or  # Command examples
            ":" in action or  # Specific guidance
            "with" in action  # Specific tools/methods
        )
        assert has_specifics, f"Action too vague: {action}"


def test_first_actions_different_for_roles():
    """Test that different roles get different first actions."""
    ceo_actions = _generate_first_actions(
        "CEO", "ceo", True, False, True, None
    )

    manager_actions = _generate_first_actions(
        "Director", "dir", False, True, True, "CEO"
    )

    worker_actions = _generate_first_actions(
        "Engineer", "eng", False, False, True, "Director"
    )

    # Actions should be different for each role
    assert ceo_actions != manager_actions
    assert manager_actions != worker_actions
    assert ceo_actions != worker_actions


def test_first_actions_different_with_without_okrs():
    """Test that actions differ based on whether OKRs exist."""
    with_okrs = _generate_first_actions(
        "CEO", "ceo", True, False, True, None
    )

    without_okrs = _generate_first_actions(
        "CEO", "ceo", True, False, False, None
    )

    # Actions should be different
    assert with_okrs != without_okrs

    # Without OKRs should focus on creating them
    assert any("Create" in a and "OKR" in a for a in without_okrs)

    # With OKRs should focus on executing them
    assert any("Review" in a and "OKR" in a for a in with_okrs)

"""
Unit tests for lifecycle state validation.
"""

import pytest

from cli.core.lifecycle import (
    CannotCloseBeadError,
    InvalidStateError,
    InvalidStateTransitionError,
    LifecycleConfig,
    get_initial_state,
    get_next_states,
    get_terminal_states,
    get_valid_states,
    parse_status_from_args,
    validate_can_close,
    validate_state_transition,
)


class TestLifecycleConfig:
    """Test LifecycleConfig class."""

    def test_for_task_type(self):
        """Should load task lifecycle configuration."""
        config = LifecycleConfig.for_type("task")

        assert config.bead_type == "task"
        assert "investigation" in config.states
        assert "done" in config.terminal
        assert "rejected" in config.terminal
        assert "planning" in config.transitions["investigation"]

    def test_for_bug_type(self):
        """Should load bug lifecycle configuration."""
        config = LifecycleConfig.for_type("bug")

        assert config.bead_type == "bug"
        assert "triage" in config.states
        assert "wontfix" in config.terminal
        assert "duplicate" in config.terminal

    def test_for_feature_type(self):
        """Should load feature lifecycle configuration."""
        config = LifecycleConfig.for_type("feature")

        assert config.bead_type == "feature"
        assert "discovery" in config.states
        assert "deferred" in config.terminal

    def test_for_unknown_type_uses_default(self):
        """Should use default lifecycle for unknown types."""
        config = LifecycleConfig.for_type("unknown")

        assert config.bead_type == "unknown"
        assert "open" in config.states
        assert "done" in config.terminal

    def test_get_initial_state(self):
        """Should return correct initial state for each type."""
        assert LifecycleConfig.for_type("task").get_initial_state() == "investigation"
        assert LifecycleConfig.for_type("bug").get_initial_state() == "triage"
        assert LifecycleConfig.for_type("feature").get_initial_state() == "discovery"
        assert LifecycleConfig.for_type("unknown").get_initial_state() == "open"

    def test_is_valid_state(self):
        """Should correctly identify valid states."""
        config = LifecycleConfig.for_type("task")

        assert config.is_valid_state("investigation")
        assert config.is_valid_state("done")
        assert config.is_valid_state("rejected")
        assert not config.is_valid_state("invalid")

    def test_is_terminal(self):
        """Should correctly identify terminal states."""
        config = LifecycleConfig.for_type("task")

        assert config.is_terminal("done")
        assert config.is_terminal("rejected")
        assert config.is_terminal("abandoned")
        assert not config.is_terminal("investigation")
        assert not config.is_terminal("review")

    def test_get_allowed_transitions(self):
        """Should return allowed transitions from a state."""
        config = LifecycleConfig.for_type("task")

        allowed = config.get_allowed_transitions("investigation")
        assert "planning" in allowed
        assert "rejected" in allowed
        assert "implementation" not in allowed

        # Terminal states have no transitions
        assert config.get_allowed_transitions("done") == []

    def test_can_transition(self):
        """Should correctly validate transitions."""
        config = LifecycleConfig.for_type("task")

        assert config.can_transition("investigation", "planning")
        assert config.can_transition("investigation", "rejected")
        assert not config.can_transition("investigation", "review")
        assert not config.can_transition("done", "investigation")


class TestValidateStateTransition:
    """Test validate_state_transition function."""

    def test_valid_transition(self):
        """Should allow valid transitions."""
        # Should not raise
        validate_state_transition(
            "bead-123", "task", "investigation", "planning"
        )
        validate_state_transition(
            "bead-123", "task", "planning", "implementation"
        )
        validate_state_transition(
            "bead-123", "task", "review", "done"
        )

    def test_invalid_transition_raises(self):
        """Should raise for invalid transitions."""
        with pytest.raises(InvalidStateTransitionError) as exc:
            validate_state_transition(
                "bead-123", "task", "investigation", "review"
            )

        assert exc.value.bead_id == "bead-123"
        assert exc.value.current_state == "investigation"
        assert exc.value.target_state == "review"
        assert "planning" in exc.value.allowed_states

    def test_transition_from_terminal_state_raises(self):
        """Should raise when trying to transition from terminal state."""
        with pytest.raises(InvalidStateTransitionError) as exc:
            validate_state_transition(
                "bead-123", "task", "done", "review"
            )

        assert exc.value.allowed_states == []
        assert "terminal" in str(exc.value).lower()

    def test_invalid_current_state_raises(self):
        """Should raise for invalid current state."""
        with pytest.raises(InvalidStateError) as exc:
            validate_state_transition(
                "bead-123", "task", "invalid", "planning"
            )

        assert exc.value.invalid_state == "invalid"

    def test_invalid_target_state_raises(self):
        """Should raise for invalid target state."""
        with pytest.raises(InvalidStateError) as exc:
            validate_state_transition(
                "bead-123", "task", "investigation", "invalid"
            )

        assert exc.value.invalid_state == "invalid"


class TestValidateCanClose:
    """Test validate_can_close function."""

    def test_can_close_terminal_state(self):
        """Should allow closing beads in terminal states."""
        # Should not raise
        validate_can_close("bead-123", "task", "done")
        validate_can_close("bead-123", "task", "rejected")
        validate_can_close("bead-123", "task", "abandoned")
        validate_can_close("bead-123", "bug", "wontfix")
        validate_can_close("bead-123", "feature", "deferred")

    def test_cannot_close_non_terminal_state(self):
        """Should raise when closing non-terminal state."""
        with pytest.raises(CannotCloseBeadError) as exc:
            validate_can_close("bead-123", "task", "review")

        assert exc.value.bead_id == "bead-123"
        assert exc.value.current_state == "review"
        assert "done" in exc.value.terminal_states
        assert "Complete the review" in str(exc.value)

    def test_actionable_error_messages(self):
        """Should provide actionable guidance in error messages."""
        # Task in investigation
        with pytest.raises(CannotCloseBeadError) as exc:
            validate_can_close("bead-123", "task", "investigation")
        assert "investigation" in str(exc.value).lower()

        # Bug in triage
        with pytest.raises(CannotCloseBeadError) as exc:
            validate_can_close("bead-123", "bug", "triage")
        assert "triage" in str(exc.value).lower()

        # Feature in design
        with pytest.raises(CannotCloseBeadError) as exc:
            validate_can_close("bead-123", "feature", "design")
        assert "implementation" in str(exc.value).lower() or "reject" in str(exc.value).lower()

    def test_invalid_state_raises(self):
        """Should raise for invalid current state."""
        with pytest.raises(InvalidStateError):
            validate_can_close("bead-123", "task", "invalid")


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_initial_state(self):
        """Should return initial state for bead types."""
        assert get_initial_state("task") == "investigation"
        assert get_initial_state("bug") == "triage"
        assert get_initial_state("feature") == "discovery"
        assert get_initial_state("unknown") == "open"

    def test_get_valid_states(self):
        """Should return all valid states including terminal."""
        states = get_valid_states("task")

        assert "investigation" in states
        assert "planning" in states
        assert "done" in states
        assert "rejected" in states

    def test_get_terminal_states(self):
        """Should return terminal states."""
        assert get_terminal_states("task") == ["done", "rejected", "abandoned"]
        assert get_terminal_states("bug") == ["done", "wontfix", "duplicate"]

    def test_get_next_states(self):
        """Should return allowed next states."""
        next_states = get_next_states("task", "investigation")
        assert "planning" in next_states
        assert "rejected" in next_states
        assert "done" not in next_states

        # Terminal state has no next states
        assert get_next_states("task", "done") == []


class TestParseStatusFromArgs:
    """Test parse_status_from_args function."""

    def test_parse_status_flag(self):
        """Should parse --status flag."""
        assert parse_status_from_args(["--status", "done"]) == "done"
        assert parse_status_from_args(["update", "--status", "review"]) == "review"

    def test_parse_status_equals(self):
        """Should parse --status=value format."""
        assert parse_status_from_args(["--status=done"]) == "done"
        assert parse_status_from_args(["update", "--status=planning"]) == "planning"

    def test_parse_state_flag(self):
        """Should parse --state flag."""
        assert parse_status_from_args(["--state", "done"]) == "done"
        assert parse_status_from_args(["--state=review"]) == "review"

    def test_parse_short_flag(self):
        """Should parse -s flag."""
        assert parse_status_from_args(["-s", "done"]) == "done"

    def test_no_status_returns_none(self):
        """Should return None when no status flag."""
        assert parse_status_from_args(["update", "bead-123"]) is None
        assert parse_status_from_args([]) is None

    def test_status_at_end_of_args(self):
        """Should parse status even at end of args list."""
        assert parse_status_from_args(["update", "bead-123", "--status"]) is None
        assert parse_status_from_args(["update", "bead-123", "--status", "done"]) == "done"


class TestBugLifecycle:
    """Test bug-specific lifecycle transitions."""

    def test_bug_triage_to_investigation(self):
        """Should allow triage to investigation."""
        validate_state_transition("bug-1", "bug", "triage", "investigation")

    def test_bug_to_wontfix(self):
        """Should allow transition to wontfix from various states."""
        validate_state_transition("bug-1", "bug", "triage", "wontfix")
        validate_state_transition("bug-1", "bug", "investigation", "wontfix")
        validate_state_transition("bug-1", "bug", "fixing", "wontfix")

    def test_bug_to_duplicate(self):
        """Should allow transition to duplicate from early states."""
        validate_state_transition("bug-1", "bug", "triage", "duplicate")
        validate_state_transition("bug-1", "bug", "investigation", "duplicate")

    def test_bug_cannot_duplicate_from_fixing(self):
        """Should not allow duplicate from fixing state."""
        with pytest.raises(InvalidStateTransitionError):
            validate_state_transition("bug-1", "bug", "fixing", "duplicate")


class TestFeatureLifecycle:
    """Test feature-specific lifecycle transitions."""

    def test_feature_discovery_to_design(self):
        """Should allow discovery to design."""
        validate_state_transition("feat-1", "feature", "discovery", "design")

    def test_feature_to_deferred(self):
        """Should allow deferring from any non-terminal state."""
        validate_state_transition("feat-1", "feature", "discovery", "deferred")
        validate_state_transition("feat-1", "feature", "design", "deferred")
        validate_state_transition("feat-1", "feature", "implementation", "deferred")
        validate_state_transition("feat-1", "feature", "review", "deferred")

    def test_feature_design_back_to_discovery(self):
        """Should allow going back to discovery from design."""
        validate_state_transition("feat-1", "feature", "design", "discovery")


class TestDefaultLifecycle:
    """Test default lifecycle for unknown bead types."""

    def test_default_open_to_in_progress(self):
        """Should allow open to in_progress."""
        validate_state_transition("bead-1", "unknown_type", "open", "in_progress")

    def test_default_can_close_from_open(self):
        """Default lifecycle allows closing from open."""
        validate_state_transition("bead-1", "unknown_type", "open", "closed")
        validate_can_close("bead-1", "unknown_type", "closed")

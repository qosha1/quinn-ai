"""Tests for centralized status classification."""
import pytest
from shared.status import (
    SessionStatusGroup,
    classify_status,
    is_working,
    is_idle,
    has_session,
    is_stopped,
    get_display_status,
    get_status_icon,
)


class TestClassifyStatus:
    """Tests for classify_status function."""

    def test_working_states(self):
        """Starting and running are classified as WORKING."""
        assert classify_status("starting") == SessionStatusGroup.WORKING
        assert classify_status("running") == SessionStatusGroup.WORKING

    def test_idle_state(self):
        """Idle is classified as IDLE."""
        assert classify_status("idle") == SessionStatusGroup.IDLE

    def test_stopped_states(self):
        """Stopped, crashed, and None are classified as STOPPED."""
        assert classify_status("stopped") == SessionStatusGroup.STOPPED
        assert classify_status("crashed") == SessionStatusGroup.STOPPED
        assert classify_status(None) == SessionStatusGroup.STOPPED

    def test_unknown_state(self):
        """Unknown states are classified as STOPPED."""
        assert classify_status("unknown") == SessionStatusGroup.STOPPED
        assert classify_status("") == SessionStatusGroup.STOPPED


class TestIsWorking:
    """Tests for is_working predicate."""

    def test_working_returns_true(self):
        """Returns True for starting and running."""
        assert is_working("starting") is True
        assert is_working("running") is True

    def test_non_working_returns_false(self):
        """Returns False for idle, stopped, crashed, None."""
        assert is_working("idle") is False
        assert is_working("stopped") is False
        assert is_working("crashed") is False
        assert is_working(None) is False


class TestIsIdle:
    """Tests for is_idle predicate."""

    def test_idle_returns_true(self):
        """Returns True only for idle."""
        assert is_idle("idle") is True

    def test_non_idle_returns_false(self):
        """Returns False for all other states."""
        assert is_idle("starting") is False
        assert is_idle("running") is False
        assert is_idle("stopped") is False
        assert is_idle("crashed") is False
        assert is_idle(None) is False


class TestHasSession:
    """Tests for has_session predicate."""

    def test_open_sessions_return_true(self):
        """Returns True for starting, running, and idle."""
        assert has_session("starting") is True
        assert has_session("running") is True
        assert has_session("idle") is True

    def test_closed_sessions_return_false(self):
        """Returns False for stopped, crashed, and None."""
        assert has_session("stopped") is False
        assert has_session("crashed") is False
        assert has_session(None) is False


class TestIsStopped:
    """Tests for is_stopped predicate."""

    def test_stopped_states_return_true(self):
        """Returns True for stopped, crashed, and None."""
        assert is_stopped("stopped") is True
        assert is_stopped("crashed") is True
        assert is_stopped(None) is True

    def test_active_states_return_false(self):
        """Returns False for starting, running, and idle."""
        assert is_stopped("starting") is False
        assert is_stopped("running") is False
        assert is_stopped("idle") is False


class TestGetDisplayStatus:
    """Tests for get_display_status function."""

    def test_working_display(self):
        """Working states show as 'Working'."""
        assert get_display_status("starting") == "Working"
        assert get_display_status("running") == "Working"

    def test_idle_display(self):
        """Idle state shows as 'Idle'."""
        assert get_display_status("idle") == "Idle"

    def test_stopped_display(self):
        """Stopped states show as 'Stopped'."""
        assert get_display_status("stopped") == "Stopped"
        assert get_display_status("crashed") == "Stopped"
        assert get_display_status(None) == "Stopped"


class TestGetStatusIcon:
    """Tests for get_status_icon function."""

    def test_working_icon(self):
        """Working states get play icon."""
        assert get_status_icon("starting") == "▶"
        assert get_status_icon("running") == "▶"

    def test_idle_icon(self):
        """Idle state gets pause icon."""
        assert get_status_icon("idle") == "⏸"

    def test_stopped_icon(self):
        """Stopped states get stop icon."""
        assert get_status_icon("stopped") == "⏹"
        assert get_status_icon("crashed") == "⏹"
        assert get_status_icon(None) == "⏹"


class TestConsistency:
    """Tests for consistency across predicates."""

    @pytest.mark.parametrize("status", ["starting", "running", "idle", "stopped", "crashed", None])
    def test_exactly_one_group(self, status):
        """Every status belongs to exactly one group."""
        working = is_working(status)
        idle = is_idle(status)
        stopped = is_stopped(status)

        # Exactly one should be True
        assert sum([working, idle, stopped]) == 1

    @pytest.mark.parametrize("status", ["starting", "running", "idle"])
    def test_has_session_iff_not_stopped(self, status):
        """has_session is True iff is_stopped is False."""
        assert has_session(status) is True
        assert is_stopped(status) is False

    @pytest.mark.parametrize("status", ["stopped", "crashed", None])
    def test_no_session_iff_stopped(self, status):
        """No session iff stopped."""
        assert has_session(status) is False
        assert is_stopped(status) is True

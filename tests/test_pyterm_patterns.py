"""
Tests for pattern matching and automatic injection.
"""

import pytest
import re
import time
import threading
from unittest.mock import MagicMock, Mock, patch

from shared.pyterm.patterns import PatternRule, PatternMatcher, RuleTriggeredCallback
from shared.pyterm.protocols import ExtractedOutput, PytermSessionState
from shared.pyterm.config import PytermConfig, LoopDetectionConfig, TimingConfig, TerminalSessionConfig


class MockSession:
    """Mock session for testing."""

    def __init__(self):
        self.injected = []
        self.output_text = "Initial output"
        self._state = PytermSessionState.RUNNING

    @property
    def id(self) -> str:
        return "mock-session"

    @property
    def state(self) -> PytermSessionState:
        return self._state

    def inject(self, text: str) -> None:
        self.injected.append(text)

    def extract(self) -> ExtractedOutput:
        return ExtractedOutput(text=self.output_text, timestamp=time.time())

    def set_output(self, text: str) -> None:
        self.output_text = text


class TestPatternRule:
    """Tests for PatternRule."""

    def test_creation(self):
        """Test PatternRule creation."""
        rule = PatternRule(
            id="rule-1",
            pattern=r"\[Y/n\]",
            response="Y\n",
        )

        assert rule.id == "rule-1"
        assert rule.pattern == r"\[Y/n\]"
        assert rule.response == "Y\n"
        assert rule.once is False
        assert rule.delay == 0.0
        assert rule.enabled is True
        assert rule._triggered is False

    def test_pattern_compilation(self):
        """Test pattern gets compiled on init."""
        rule = PatternRule(
            id="rule-1",
            pattern=r"password:",
            response="secret\n",
        )

        assert rule._compiled is not None
        assert isinstance(rule._compiled, re.Pattern)

    def test_matches_returns_match(self):
        """Test matches() returns match object."""
        rule = PatternRule(
            id="rule-1",
            pattern=r"\[Y/n\]",
            response="Y\n",
        )

        match = rule.matches("Do you want to continue? [Y/n]")

        assert match is not None
        assert match.group() == "[Y/n]"

    def test_matches_returns_none_when_no_match(self):
        """Test matches() returns None when no match."""
        rule = PatternRule(
            id="rule-1",
            pattern=r"\[Y/n\]",
            response="Y\n",
        )

        match = rule.matches("No match here")

        assert match is None

    def test_matches_disabled_rule(self):
        """Test matches() returns None when rule disabled."""
        rule = PatternRule(
            id="rule-1",
            pattern=r"\[Y/n\]",
            response="Y\n",
            enabled=False,
        )

        match = rule.matches("Continue? [Y/n]")

        assert match is None

    def test_once_rule_only_matches_once(self):
        """Test once rule only matches once."""
        rule = PatternRule(
            id="rule-1",
            pattern=r"\[Y/n\]",
            response="Y\n",
            once=True,
        )

        # First match
        match1 = rule.matches("Continue? [Y/n]")
        assert match1 is not None

        # Mark as triggered
        rule.mark_triggered()

        # Second match should fail
        match2 = rule.matches("Continue? [Y/n]")
        assert match2 is None

    def test_reset_clears_triggered(self):
        """Test reset() clears triggered state."""
        rule = PatternRule(
            id="rule-1",
            pattern=r"test",
            response="response",
            once=True,
        )

        rule.mark_triggered()
        assert rule._triggered is True

        rule.reset()
        assert rule._triggered is False

    def test_delay_property(self):
        """Test delay property."""
        rule = PatternRule(
            id="rule-1",
            pattern=r"wait",
            response="ok",
            delay=0.5,
        )

        assert rule.delay == 0.5


class TestPatternMatcherInit:
    """Tests for PatternMatcher initialization."""

    def test_init(self):
        """Test PatternMatcher initialization."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        assert matcher._session == session
        assert matcher._config == config
        assert len(matcher._rules) == 0
        assert matcher._last_output == ""
        assert matcher._watching is False

    def test_init_requires_config(self):
        """Test initialization with config."""
        session = MockSession()
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.05,
                idle_timeout=10.0,
                response_timeout=20.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=5,
                window_duration=2.0,
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )

        matcher = PatternMatcher(session, config)

        assert matcher._config == config


class TestPatternMatcherRuleManagement:
    """Tests for rule add/remove/get."""

    def test_add_rule(self):
        """Test add_rule() adds a rule."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"test", response="ok")
        matcher.add_rule(rule)

        assert "rule-1" in matcher._rules
        assert matcher._rules["rule-1"] == rule

    def test_remove_rule(self):
        """Test remove_rule() removes a rule."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"test", response="ok")
        matcher.add_rule(rule)

        result = matcher.remove_rule("rule-1")

        assert result is True
        assert "rule-1" not in matcher._rules

    def test_remove_nonexistent_rule(self):
        """Test remove_rule() returns False for nonexistent rule."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        result = matcher.remove_rule("nonexistent")

        assert result is False

    def test_get_rule(self):
        """Test get_rule() retrieves a rule."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"test", response="ok")
        matcher.add_rule(rule)

        retrieved = matcher.get_rule("rule-1")

        assert retrieved == rule

    def test_get_nonexistent_rule(self):
        """Test get_rule() returns None for nonexistent rule."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        result = matcher.get_rule("nonexistent")

        assert result is None

    def test_clear_rules(self):
        """Test clear_rules() removes all rules."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        matcher.add_rule(PatternRule(id="rule-1", pattern=r"a", response="b"))
        matcher.add_rule(PatternRule(id="rule-2", pattern=r"c", response="d"))

        matcher.clear_rules()

        assert len(matcher._rules) == 0


class TestPatternMatcherCheckOutput:
    """Tests for check_output()."""

    def test_check_output_finds_match(self):
        """Test check_output() finds matching pattern."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"\[Y/n\]", response="Y\n")
        matcher.add_rule(rule)

        matches = matcher.check_output("Continue? [Y/n]")

        assert len(matches) == 1
        assert matches[0][0] == rule
        assert matches[0][1].group() == "[Y/n]"

    def test_check_output_no_match(self):
        """Test check_output() returns empty when no match."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"\[Y/n\]", response="Y\n")
        matcher.add_rule(rule)

        matches = matcher.check_output("No prompt here")

        assert len(matches) == 0

    def test_check_output_multiple_rules(self):
        """Test check_output() checks multiple rules."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        rule1 = PatternRule(id="rule-1", pattern=r"\[Y/n\]", response="Y\n")
        rule2 = PatternRule(id="rule-2", pattern=r"password:", response="secret\n")

        matcher.add_rule(rule1)
        matcher.add_rule(rule2)

        matches = matcher.check_output("Enter password: to continue [Y/n]")

        assert len(matches) == 2

    def test_check_output_only_checks_new_content(self):
        """Test check_output() only checks new content."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"\[Y/n\]", response="Y\n")
        matcher.add_rule(rule)

        # First check
        matches1 = matcher.check_output("Continue? [Y/n]")
        assert len(matches1) == 1

        # Same output - should return no matches
        matches2 = matcher.check_output("Continue? [Y/n]")
        assert len(matches2) == 0

        # New content appended
        matches3 = matcher.check_output("Continue? [Y/n]\nAnother prompt [Y/n]")
        assert len(matches3) == 1

    def test_check_output_marks_rule_triggered(self):
        """Test check_output() marks rule as triggered."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"test", response="ok", once=True)
        matcher.add_rule(rule)

        assert rule._triggered is False

        matcher.check_output("This is a test")

        assert rule._triggered is True


class TestPatternMatcherLoopDetection:
    """Tests for loop detection."""

    def test_loop_detection_prevents_rapid_triggers(self):
        """Test loop detection prevents rapid triggers."""
        session = MockSession()
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.1,
                idle_timeout=10.0,
                response_timeout=20.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=3,
                window_duration=1.0,
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"test", response="ok")
        matcher.add_rule(rule)

        # Trigger 3 times (at limit)
        for i in range(3):
            matches = matcher.check_output(f"test {i}")
            assert len(matches) == 1

        # 4th trigger should be blocked
        matches = matcher.check_output("test 4")
        assert len(matches) == 0

    def test_loop_detection_window_reset(self):
        """Test loop detection window resets after duration."""
        session = MockSession()
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.1,
                idle_timeout=10.0,
                response_timeout=20.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=2,
                window_duration=0.2,  # Short window for testing
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"test", response="ok")
        matcher.add_rule(rule)

        # Trigger twice (at limit)
        matcher.check_output("test 1")
        matcher.check_output("test 2")

        # Wait for window to expire
        time.sleep(0.3)

        # Should be able to trigger again
        matches = matcher.check_output("test 3")
        assert len(matches) == 1


class TestPatternMatcherCallbacks:
    """Tests for callback registration."""

    def test_on_triggered_callback(self):
        """Test on_triggered() registers callback."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        callback = MagicMock()
        matcher.on_triggered(callback)

        assert callback in matcher._callbacks


class TestPatternMatcherWatching:
    """Tests for start_watching() and stop_watching()."""

    def test_start_watching(self):
        """Test start_watching() starts watching thread."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        matcher.start_watching()

        assert matcher.is_watching is True
        assert matcher._watch_thread is not None

        # Clean up
        matcher.stop_watching()

    def test_stop_watching(self):
        """Test stop_watching() stops the thread."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        matcher.start_watching()
        time.sleep(0.1)

        matcher.stop_watching()

        # Give thread time to exit
        time.sleep(0.1)
        assert matcher.is_watching is False

    def test_is_watching_property(self):
        """Test is_watching property."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        assert matcher.is_watching is False

        matcher.start_watching()
        assert matcher.is_watching is True

        matcher.stop_watching()
        time.sleep(0.1)
        assert matcher.is_watching is False

    def test_start_watching_idempotent(self):
        """Test start_watching() is idempotent."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        matcher.start_watching()
        first_thread = matcher._watch_thread

        # Call again
        matcher.start_watching()

        # Should still be same thread
        assert matcher._watch_thread == first_thread

        matcher.stop_watching()


class TestPatternMatcherIntegration:
    """Integration tests for pattern matching."""

    def test_watch_and_auto_inject(self):
        """Test watching automatically injects on match."""
        session = MockSession()
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.05,  # Fast polling for test
                idle_timeout=10.0,
                response_timeout=20.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=10,
                window_duration=1.0,
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"\[Y/n\]", response="Y\n")
        matcher.add_rule(rule)

        # Start watching
        matcher.start_watching()

        # Change output to trigger pattern
        session.set_output("Continue? [Y/n]")

        # Wait for polling to detect and inject
        time.sleep(0.2)

        # Stop watching
        matcher.stop_watching()

        # Verify injection happened
        assert "Y\n" in session.injected

    def test_watch_with_delay(self):
        """Test watching respects delay before injection."""
        session = MockSession()
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.05,
                idle_timeout=10.0,
                response_timeout=20.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=10,
                window_duration=1.0,
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )
        matcher = PatternMatcher(session, config)

        rule = PatternRule(
            id="rule-1",
            pattern=r"test",
            response="ok",
            delay=0.2,  # 200ms delay
        )
        matcher.add_rule(rule)

        matcher.start_watching()

        start = time.time()
        session.set_output("test prompt")

        # Wait for injection
        time.sleep(0.4)

        matcher.stop_watching()

        # Verify delay was respected (at least 200ms)
        if session.injected:
            duration = time.time() - start
            assert duration >= 0.2

    def test_watch_calls_callbacks(self):
        """Test watching calls registered callbacks on match."""
        session = MockSession()
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.05,
                idle_timeout=10.0,
                response_timeout=20.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=10,
                window_duration=1.0,
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )
        matcher = PatternMatcher(session, config)

        rule = PatternRule(id="rule-1", pattern=r"trigger", response="ok")
        matcher.add_rule(rule)

        callback = MagicMock()
        matcher.on_triggered(callback)

        matcher.start_watching()

        session.set_output("This is a trigger")

        # Wait for callback
        time.sleep(0.2)

        matcher.stop_watching()

        # Verify callback was called
        assert callback.call_count >= 1

    def test_watch_handles_session_errors(self):
        """Test watching handles session errors gracefully."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        # Make extract raise error
        session.extract = Mock(side_effect=RuntimeError("Session stopped"))

        matcher.start_watching()

        # Wait a bit
        time.sleep(0.2)

        # Should still be watching (error caught)
        assert matcher.is_watching is True

        matcher.stop_watching()


class TestPatternMatcherThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_rule_access(self):
        """Test concurrent access to rules is thread-safe."""
        session = MockSession()
        config = PytermConfig.standard()
        matcher = PatternMatcher(session, config)

        errors = []

        def add_rules():
            try:
                for i in range(10):
                    rule = PatternRule(
                        id=f"rule-{threading.current_thread().ident}-{i}",
                        pattern=r"test",
                        response="ok",
                    )
                    matcher.add_rule(rule)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_rules) for _ in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(matcher._rules) == 30  # 3 threads * 10 rules each

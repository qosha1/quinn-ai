"""
Tests for pyterm configuration classes.
"""

import pytest

from shared.pyterm.config import (
    TimingConfig,
    LoopDetectionConfig,
    TerminalSessionConfig,
    PytermConfig,
    validate_timing_config,
    validate_config,
)


class TestTimingConfig:
    """Tests for TimingConfig."""

    def test_creation(self):
        """Test TimingConfig creation."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        assert config.poll_interval == 0.1
        assert config.idle_timeout == 300.0
        assert config.response_timeout == 600.0
        assert config.stop_grace_period == 0.5

    def test_frozen(self):
        """Test TimingConfig is frozen (immutable)."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        with pytest.raises(AttributeError):
            config.poll_interval = 0.2


class TestLoopDetectionConfig:
    """Tests for LoopDetectionConfig."""

    def test_creation(self):
        """Test LoopDetectionConfig creation."""
        config = LoopDetectionConfig(
            max_triggers_per_window=10,
            window_duration=1.0,
        )

        assert config.max_triggers_per_window == 10
        assert config.window_duration == 1.0

    def test_frozen(self):
        """Test LoopDetectionConfig is frozen."""
        config = LoopDetectionConfig(
            max_triggers_per_window=10,
            window_duration=1.0,
        )

        with pytest.raises(AttributeError):
            config.max_triggers_per_window = 20


class TestTerminalSessionConfig:
    """Tests for TerminalSessionConfig."""

    def test_creation(self):
        """Test TerminalSessionConfig creation."""
        config = TerminalSessionConfig(
            cancel_signal="\x03",
            default_cols=80,
            default_rows=24,
            default_shell="/bin/bash",
        )

        assert config.cancel_signal == "\x03"
        assert config.default_cols == 80
        assert config.default_rows == 24
        assert config.default_shell == "/bin/bash"

    def test_frozen(self):
        """Test TerminalSessionConfig is frozen."""
        config = TerminalSessionConfig(
            cancel_signal="\x03",
            default_cols=80,
            default_rows=24,
            default_shell="/bin/bash",
        )

        with pytest.raises(AttributeError):
            config.default_cols = 120


class TestPytermConfig:
    """Tests for PytermConfig."""

    def test_creation(self):
        """Test PytermConfig creation."""
        timing = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        loop_detection = LoopDetectionConfig(
            max_triggers_per_window=10,
            window_duration=1.0,
        )

        session = TerminalSessionConfig(
            cancel_signal="\x03",
            default_cols=80,
            default_rows=24,
            default_shell="/bin/bash",
        )

        config = PytermConfig(
            timing=timing,
            loop_detection=loop_detection,
            session=session,
        )

        assert config.timing == timing
        assert config.loop_detection == loop_detection
        assert config.session == session

    def test_frozen(self):
        """Test PytermConfig is frozen."""
        config = PytermConfig.standard()

        with pytest.raises(AttributeError):
            config.timing = TimingConfig(
                poll_interval=0.2,
                idle_timeout=100.0,
                response_timeout=200.0,
                stop_grace_period=1.0,
            )

    def test_standard_factory(self):
        """Test standard() factory method."""
        config = PytermConfig.standard()

        assert config.timing.poll_interval == 0.1
        assert config.timing.idle_timeout == 300.0
        assert config.timing.response_timeout == 600.0
        assert config.timing.stop_grace_period == 0.5

        assert config.loop_detection.max_triggers_per_window == 10
        assert config.loop_detection.window_duration == 1.0

        assert config.session.cancel_signal == "\x03"
        assert config.session.default_cols == 80
        assert config.session.default_rows == 24
        assert config.session.default_shell == "/bin/bash"

    def test_to_dict(self):
        """Test to_dict() serialization."""
        config = PytermConfig.standard()

        d = config.to_dict()

        assert "timing" in d
        assert d["timing"]["poll_interval"] == 0.1
        assert d["timing"]["idle_timeout"] == 300.0

        assert "loop_detection" in d
        assert d["loop_detection"]["max_triggers_per_window"] == 10

        assert "session" in d
        assert d["session"]["default_cols"] == 80
        assert d["session"]["default_shell"] == "/bin/bash"

    def test_to_dict_cancel_signal_repr(self):
        """Test to_dict() uses repr for cancel_signal."""
        config = PytermConfig.standard()

        d = config.to_dict()

        # Cancel signal should be represented as string repr
        assert "\\x03" in d["session"]["cancel_signal"]


class TestValidateTimingConfig:
    """Tests for validate_timing_config()."""

    def test_valid_config_no_errors(self):
        """Test valid config returns no errors."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        assert errors == []

    def test_negative_poll_interval(self):
        """Test negative poll_interval is invalid."""
        config = TimingConfig(
            poll_interval=-0.1,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        assert len(errors) > 0
        assert any("poll_interval must be positive" in e for e in errors)

    def test_zero_poll_interval(self):
        """Test zero poll_interval is invalid."""
        config = TimingConfig(
            poll_interval=0.0,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        assert any("poll_interval must be positive" in e for e in errors)

    def test_too_large_poll_interval(self):
        """Test very large poll_interval triggers warning."""
        config = TimingConfig(
            poll_interval=15.0,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        assert any("too large" in e for e in errors)

    def test_negative_idle_timeout(self):
        """Test negative idle_timeout is invalid."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=-10.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        assert any("idle_timeout must be positive" in e for e in errors)

    def test_negative_response_timeout(self):
        """Test negative response_timeout is invalid."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=-100.0,
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        assert any("response_timeout must be positive" in e for e in errors)

    def test_response_timeout_less_than_idle(self):
        """Test response_timeout < idle_timeout triggers warning."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=100.0,  # Less than idle_timeout
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        assert any("response_timeout should be >=" in e for e in errors)

    def test_negative_stop_grace_period(self):
        """Test negative stop_grace_period is invalid."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=-0.5,
        )

        errors = validate_timing_config(config)

        assert any("stop_grace_period must be non-negative" in e for e in errors)

    def test_multiple_errors(self):
        """Test multiple errors are all returned."""
        config = TimingConfig(
            poll_interval=-0.1,
            idle_timeout=-300.0,
            response_timeout=-600.0,
            stop_grace_period=-0.5,
        )

        errors = validate_timing_config(config)

        assert len(errors) >= 4


class TestValidateConfig:
    """Tests for validate_config()."""

    def test_valid_config_no_errors(self):
        """Test valid config returns no errors."""
        config = PytermConfig.standard()

        errors = validate_config(config)

        assert errors == []

    def test_validates_timing_config(self):
        """Test validate_config() validates timing config."""
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=-0.1,  # Invalid
                idle_timeout=300.0,
                response_timeout=600.0,
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

        errors = validate_config(config)

        assert any("poll_interval" in e for e in errors)

    def test_validates_loop_detection(self):
        """Test validate_config() validates loop detection config."""
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.1,
                idle_timeout=300.0,
                response_timeout=600.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=-10,  # Invalid
                window_duration=1.0,
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )

        errors = validate_config(config)

        assert any("max_triggers_per_window must be positive" in e for e in errors)

    def test_validates_window_duration(self):
        """Test validate_config() validates window_duration."""
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.1,
                idle_timeout=300.0,
                response_timeout=600.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=10,
                window_duration=-1.0,  # Invalid
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )

        errors = validate_config(config)

        assert any("window_duration must be positive" in e for e in errors)

    def test_validates_default_cols(self):
        """Test validate_config() validates default_cols."""
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.1,
                idle_timeout=300.0,
                response_timeout=600.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=10,
                window_duration=1.0,
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=-80,  # Invalid
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )

        errors = validate_config(config)

        assert any("default_cols must be positive" in e for e in errors)

    def test_validates_default_rows(self):
        """Test validate_config() validates default_rows."""
        config = PytermConfig(
            timing=TimingConfig(
                poll_interval=0.1,
                idle_timeout=300.0,
                response_timeout=600.0,
                stop_grace_period=0.5,
            ),
            loop_detection=LoopDetectionConfig(
                max_triggers_per_window=10,
                window_duration=1.0,
            ),
            session=TerminalSessionConfig(
                cancel_signal="\x03",
                default_cols=80,
                default_rows=0,  # Invalid
                default_shell="/bin/bash",
            ),
        )

        errors = validate_config(config)

        assert any("default_rows must be positive" in e for e in errors)


class TestConfigEdgeCases:
    """Tests for edge cases and unusual configurations."""

    def test_very_small_poll_interval(self):
        """Test very small poll interval (valid but unusual)."""
        config = TimingConfig(
            poll_interval=0.001,  # 1ms
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        # Should be valid (no minimum besides > 0)
        assert errors == []

    def test_very_large_timeouts(self):
        """Test very large timeout values."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=86400.0,  # 24 hours
            response_timeout=172800.0,  # 48 hours
            stop_grace_period=60.0,
        )

        errors = validate_timing_config(config)

        # Should be valid (unusual but not wrong)
        assert errors == []

    def test_zero_stop_grace_period(self):
        """Test zero stop_grace_period is valid."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=600.0,
            stop_grace_period=0.0,
        )

        errors = validate_timing_config(config)

        # Zero is valid (non-negative)
        assert errors == []

    def test_equal_idle_and_response_timeout(self):
        """Test equal idle and response timeouts."""
        config = TimingConfig(
            poll_interval=0.1,
            idle_timeout=300.0,
            response_timeout=300.0,  # Equal to idle
            stop_grace_period=0.5,
        )

        errors = validate_timing_config(config)

        # Should be valid (>= not just >)
        assert errors == []

    def test_custom_shell(self):
        """Test custom shell configuration."""
        config = TerminalSessionConfig(
            cancel_signal="\x03",
            default_cols=120,
            default_rows=40,
            default_shell="/bin/zsh",
        )

        assert config.default_shell == "/bin/zsh"

    def test_custom_cancel_signal(self):
        """Test custom cancel signal."""
        config = TerminalSessionConfig(
            cancel_signal="\x1b",  # ESC instead of Ctrl+C
            default_cols=80,
            default_rows=24,
            default_shell="/bin/bash",
        )

        assert config.cancel_signal == "\x1b"

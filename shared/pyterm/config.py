"""
pyterm configuration - Explicit configuration with no magic values.

All timing values, thresholds, and behavioral settings are defined here.
No defaults - configuration must be explicitly provided.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TimingConfig:
    """
    Timing configuration for pyterm operations.

    All values are in seconds unless otherwise noted.
    No defaults - must be explicitly set.
    """

    poll_interval: float
    """Interval between output polls (seconds)."""

    idle_timeout: float
    """Maximum time to wait for idle state (seconds)."""

    response_timeout: float
    """Maximum time to wait for a response (seconds)."""

    stop_grace_period: float
    """Time to wait for graceful shutdown before force kill (seconds)."""


@dataclass(frozen=True)
class LoopDetectionConfig:
    """Configuration for pattern matching loop detection."""

    max_triggers_per_window: int
    """Maximum rule triggers allowed in the time window."""

    window_duration: float
    """Duration of the detection window (seconds)."""


@dataclass(frozen=True)
class TerminalSessionConfig:
    """Configuration for terminal session behavior.

    Note: This is distinct from shared.core.SessionConfig which handles
    session spawning configuration. This class handles terminal-specific
    behavior settings.
    """

    cancel_signal: str
    """Signal to send for cancellation (e.g., Ctrl+C)."""

    default_cols: int
    """Default terminal columns."""

    default_rows: int
    """Default terminal rows."""

    default_shell: str
    """Default shell to use."""


@dataclass(frozen=True)
class PytermConfig:
    """
    Complete pyterm configuration.

    This is the single source of truth for all configurable values.
    Must be explicitly constructed - no discovery or defaults.

    Example:
        config = PytermConfig.standard()  # Get standard config
        config = PytermConfig(            # Or build custom
            timing=TimingConfig(...),
            loop_detection=LoopDetectionConfig(...),
            session=TerminalSessionConfig(...),
        )
    """

    timing: TimingConfig
    loop_detection: LoopDetectionConfig
    session: TerminalSessionConfig

    @classmethod
    def standard(cls) -> "PytermConfig":
        """
        Create standard configuration with sensible values.

        Use this when you don't need custom configuration.
        All values are explicit and documented.
        """
        return cls(
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
                cancel_signal="\x03",  # Ctrl+C
                default_cols=80,
                default_rows=24,
                default_shell="/bin/bash",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize config to dict."""
        return {
            "timing": {
                "poll_interval": self.timing.poll_interval,
                "idle_timeout": self.timing.idle_timeout,
                "response_timeout": self.timing.response_timeout,
                "stop_grace_period": self.timing.stop_grace_period,
            },
            "loop_detection": {
                "max_triggers_per_window": self.loop_detection.max_triggers_per_window,
                "window_duration": self.loop_detection.window_duration,
            },
            "session": {
                "cancel_signal": repr(self.session.cancel_signal),
                "default_cols": self.session.default_cols,
                "default_rows": self.session.default_rows,
                "default_shell": self.session.default_shell,
            },
        }


# =============================================================================
# Validation
# =============================================================================

def validate_timing_config(config: TimingConfig) -> list[str]:
    """Validate timing configuration. Returns list of errors."""
    errors = []

    if config.poll_interval <= 0:
        errors.append("poll_interval must be positive")
    if config.poll_interval > 10:
        errors.append("poll_interval seems too large (> 10s)")

    if config.idle_timeout <= 0:
        errors.append("idle_timeout must be positive")

    if config.response_timeout <= 0:
        errors.append("response_timeout must be positive")

    if config.response_timeout < config.idle_timeout:
        errors.append("response_timeout should be >= idle_timeout")

    if config.stop_grace_period < 0:
        errors.append("stop_grace_period must be non-negative")

    return errors


def validate_config(config: PytermConfig) -> list[str]:
    """Validate full configuration. Returns list of errors."""
    errors = validate_timing_config(config.timing)

    if config.loop_detection.max_triggers_per_window <= 0:
        errors.append("max_triggers_per_window must be positive")

    if config.loop_detection.window_duration <= 0:
        errors.append("window_duration must be positive")

    if config.session.default_cols <= 0:
        errors.append("default_cols must be positive")

    if config.session.default_rows <= 0:
        errors.append("default_rows must be positive")

    return errors

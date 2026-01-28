"""
Claude Code state monitor implementation.

Detects state from Claude Code CLI's ANSI output patterns using ClaudeCodeParser.
"""

import logging
import threading
import time
import uuid
from typing import Optional

from shared.pyterm.state_monitor import (
    StateMonitor,
    StateMonitorConfig,
    MonitoringMode,
    StateChangeCallback,
    StateDetectionError,
)
from shared.pyterm.protocols import Session, SessionState
from shared.pyterm.parsers.claude_code import ClaudeCodeParser
from shared.pyterm.agent_state import AgentState

logger = logging.getLogger(__name__)


class ClaudeCodeStateMonitor(StateMonitor):
    """State monitor for Claude Code CLI.

    Uses ClaudeCodeParser to detect state from terminal output.
    Supports background polling and explicit polling modes.
    """

    def __init__(self, config: StateMonitorConfig, session: Session):
        """Initialize Claude Code state monitor.

        Args:
            config: Monitoring configuration
            session: Session to monitor (must be a pyterm Session)
        """
        self._config = config
        self._session = session
        self._parser = ClaudeCodeParser()

        # State tracking
        self._current_state = SessionState.IDLE
        self._last_activity = time.time()
        self._lock = threading.RLock()

        # Callback management
        self._callbacks: dict[str, StateChangeCallback] = {}

        # Background monitoring
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._is_monitoring = False

        # Statistics
        self._poll_count = 0
        self._state_change_count = 0
        self._error_count = 0
        self._consecutive_errors = 0
        self._last_poll_time: Optional[float] = None

    def start_monitoring(self) -> None:
        """Start monitoring according to configured mode."""
        with self._lock:
            if self._is_monitoring:
                logger.debug("Monitoring already active")
                return

            self._is_monitoring = True
            self._stop_flag.clear()

            if self._config.mode == MonitoringMode.BACKGROUND:
                self._monitor_thread = threading.Thread(
                    target=self._background_monitor_loop,
                    name=f"StateMonitor-{id(self._session)}",
                    daemon=True,
                )
                self._monitor_thread.start()
                logger.info(f"Started background monitoring for session")

            elif self._config.mode == MonitoringMode.EXPLICIT:
                logger.info(f"Started explicit monitoring for session")

            elif self._config.mode == MonitoringMode.CALLBACK:
                # Claude Code doesn't have native events, fall back to polling
                logger.warning("Claude Code doesn't support callback mode, using background polling")
                self._config = StateMonitorConfig(
                    mode=MonitoringMode.BACKGROUND,
                    poll_interval=self._config.poll_interval,
                    idle_timeout=self._config.idle_timeout,
                )
                self.start_monitoring()

    def stop_monitoring(self) -> None:
        """Stop monitoring and cleanup."""
        with self._lock:
            if not self._is_monitoring:
                return

            self._is_monitoring = False
            self._stop_flag.set()

        # Join thread outside lock to avoid deadlock
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
            if self._monitor_thread.is_alive():
                logger.warning(f"Monitor thread did not stop cleanly")

        logger.info(f"Stopped monitoring for session")

    def poll(self) -> SessionState:
        """Poll session and detect current state."""
        with self._lock:
            self._poll_count += 1
            self._last_poll_time = time.time()

        try:
            # Extract session output
            output = self._session.extract()

            # Detect state using parser
            agent_state = self._parser.detect_state(output.text)

            # Map agent state to session state
            new_session_state = self._map_agent_to_session_state(agent_state)

            # Check for state change
            with self._lock:
                old_state = self._current_state
                if new_session_state != old_state:
                    self._current_state = new_session_state
                    self._state_change_count += 1

                    # Copy callbacks to invoke outside lock
                    callbacks = list(self._callbacks.values())

            # Notify subscribers (outside lock)
            if new_session_state != old_state:
                self._notify_subscribers(old_state, new_session_state, callbacks)

            # Reset error count on successful poll
            with self._lock:
                self._consecutive_errors = 0

            return new_session_state

        except Exception as e:
            with self._lock:
                self._error_count += 1
                self._consecutive_errors += 1
            logger.error(f"State detection error: {e}")
            raise StateDetectionError(f"Failed to detect state: {e}")

    def subscribe(self, callback: StateChangeCallback) -> str:
        """Subscribe to state changes."""
        subscription_id = f"sub-{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._callbacks[subscription_id] = callback
        logger.debug(f"Added subscription {subscription_id}")
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove subscription."""
        with self._lock:
            if subscription_id in self._callbacks:
                del self._callbacks[subscription_id]
                logger.debug(f"Removed subscription {subscription_id}")

    @property
    def current_state(self) -> SessionState:
        """Get last known state."""
        with self._lock:
            return self._current_state

    @property
    def is_monitoring(self) -> bool:
        """Check if monitoring is active."""
        with self._lock:
            return self._is_monitoring

    def get_stats(self) -> dict:
        """Get monitoring statistics."""
        with self._lock:
            return {
                "poll_count": self._poll_count,
                "state_changes": self._state_change_count,
                "last_poll_time": self._last_poll_time,
                "error_count": self._error_count,
                "consecutive_errors": self._consecutive_errors,
                "mode": self._config.mode.value,
                "poll_interval": self._config.poll_interval,
            }

    def _background_monitor_loop(self) -> None:
        """Background polling thread main loop."""
        logger.info(f"Background monitor started")

        while not self._stop_flag.is_set():
            try:
                self.poll()

                # Sleep for poll interval, checking stop flag frequently
                sleep_remaining = self._config.poll_interval
                while sleep_remaining > 0 and not self._stop_flag.is_set():
                    sleep_chunk = min(0.1, sleep_remaining)
                    time.sleep(sleep_chunk)
                    sleep_remaining -= sleep_chunk

            except StateDetectionError as e:
                logger.error(f"Poll failed: {e}")

                # Check if we should stop due to too many errors
                with self._lock:
                    if self._consecutive_errors >= self._config.max_consecutive_errors:
                        logger.error(
                            f"Stopping monitor after {self._consecutive_errors} consecutive errors"
                        )
                        self._is_monitoring = False
                        break

                # Wait before retry
                time.sleep(self._config.error_retry_interval)

        logger.info(f"Background monitor stopped")

    def _map_agent_to_session_state(self, agent_state: AgentState) -> SessionState:
        """Map pyterm AgentState to SessionState."""
        mapping = {
            AgentState.IDLE: SessionState.IDLE,
            AgentState.THINKING: SessionState.RUNNING,
            AgentState.EXECUTING_TOOL: SessionState.RUNNING,
            AgentState.WAITING_INPUT: SessionState.RUNNING,
            AgentState.ERROR: SessionState.ERROR,
            AgentState.PAUSED: SessionState.IDLE,
        }

        return mapping.get(agent_state, SessionState.IDLE)

    def _notify_subscribers(
        self,
        old_state: SessionState,
        new_state: SessionState,
        callbacks: list[StateChangeCallback],
    ) -> None:
        """Notify all subscribers of state change."""
        for callback in callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error(f"State change callback failed: {e}", exc_info=True)

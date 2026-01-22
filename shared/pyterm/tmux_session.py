"""
TmuxSession - Session implementation using tmux.

Uses subprocess calls to tmux for session management.
"""

import subprocess
import threading
import time
import uuid
from typing import Callable

from shared.pyterm.protocols import (
    ExtractedOutput,
    Session,
    SessionConfig,
    SessionState,
)
from shared.pyterm.config import PytermConfig


class TmuxSession:
    """
    Session implementation using tmux.

    Each TmuxSession wraps a tmux session with a unique name.
    """

    def __init__(
        self,
        session_name: str | None = None,
        config: PytermConfig | None = None,
    ):
        """
        Initialize TmuxSession.

        Args:
            session_name: Name for the tmux session (auto-generated if None)
            config: Pyterm configuration (uses standard if None for backwards compat)
        """
        self._id = session_name or f"pyterm-{uuid.uuid4().hex[:8]}"
        self._config = config or PytermConfig.standard()
        self._state = SessionState.IDLE
        self._pid: int | None = None
        self._session_config: SessionConfig | None = None
        self._output_callbacks: list[Callable[[ExtractedOutput], None]] = []
        self._state_callbacks: list[Callable[[SessionState, SessionState], None]] = []
        self._polling_thread: threading.Thread | None = None
        self._stop_polling = threading.Event()

    @property
    def id(self) -> str:
        return self._id

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def pid(self) -> int | None:
        return self._pid

    def _set_state(self, new_state: SessionState) -> None:
        """Set state and notify callbacks."""
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            for cb in self._state_callbacks:
                cb(old_state, new_state)

    def _run_tmux(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a tmux command."""
        cmd = ["tmux"] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def _session_exists(self) -> bool:
        """Check if tmux session exists."""
        result = self._run_tmux("has-session", "-t", self._id, check=False)
        return result.returncode == 0

    def start(self, config: SessionConfig | None = None) -> None:
        """Start the tmux session."""
        if self._state == SessionState.RUNNING:
            raise RuntimeError(f"Session {self._id} already running")

        # Use provided config or build from pyterm config
        if config:
            self._session_config = config
        else:
            self._session_config = SessionConfig(
                shell=self._config.session.default_shell,
                cols=self._config.session.default_cols,
                rows=self._config.session.default_rows,
            )

        # Build tmux new-session command
        cmd_args = [
            "new-session",
            "-d",  # detached
            "-s", self._id,  # session name
            "-x", str(self._session_config.cols),
            "-y", str(self._session_config.rows),
        ]

        if self._session_config.cwd:
            cmd_args.extend(["-c", self._session_config.cwd])

        # Set shell command
        shell_cmd = self._session_config.shell
        if self._session_config.args:
            shell_cmd = f"{shell_cmd} {' '.join(self._session_config.args)}"
        cmd_args.append(shell_cmd)

        # Set environment variables
        for key, value in self._session_config.env.items():
            self._run_tmux("set-environment", "-t", self._id, key, value, check=False)

        self._run_tmux(*cmd_args)

        # Get the shell PID
        result = self._run_tmux(
            "display-message", "-t", self._id, "-p", "#{pane_pid}"
        )
        self._pid = int(result.stdout.strip()) if result.stdout.strip() else None

        self._set_state(SessionState.RUNNING)

    def stop(self, force: bool = False) -> None:
        """Stop the tmux session."""
        if self._state != SessionState.RUNNING:
            return

        self._stop_polling.set()

        grace_period = self._config.timing.stop_grace_period

        if force:
            self._run_tmux("kill-session", "-t", self._id, check=False)
        else:
            # Send exit command first
            self.inject("exit\n")
            time.sleep(grace_period)
            # Then kill if still exists
            if self._session_exists():
                self._run_tmux("kill-session", "-t", self._id, check=False)

        self._pid = None
        self._set_state(SessionState.EXITED)

    def inject(self, text: str) -> None:
        """Inject text into the session."""
        if self._state != SessionState.RUNNING:
            raise RuntimeError(f"Session {self._id} not running")

        # Use send-keys with literal flag for exact text
        self._run_tmux("send-keys", "-t", self._id, "-l", text)

    def inject_keys(self, keys: list[str]) -> None:
        """Inject key sequences."""
        if self._state != SessionState.RUNNING:
            raise RuntimeError(f"Session {self._id} not running")

        # send-keys without -l interprets key names
        for key in keys:
            self._run_tmux("send-keys", "-t", self._id, key)

    def extract(self) -> ExtractedOutput:
        """Extract current screen content."""
        if self._state != SessionState.RUNNING:
            raise RuntimeError(f"Session {self._id} not running")

        # capture-pane gets visible content
        result = self._run_tmux(
            "capture-pane", "-t", self._id, "-p"  # -p prints to stdout
        )

        return ExtractedOutput(
            text=result.stdout,
            timestamp=time.time(),
            raw=result.stdout.encode() if result.stdout else None,
        )

    def extract_history(self, lines: int | None = None) -> list[str]:
        """Extract scrollback history."""
        if self._state != SessionState.RUNNING:
            raise RuntimeError(f"Session {self._id} not running")

        args = ["capture-pane", "-t", self._id, "-p", "-S", "-"]  # -S - = start of history

        if lines:
            args.extend(["-E", str(lines)])  # -E = end line

        result = self._run_tmux(*args)
        return result.stdout.splitlines() if result.stdout else []

    def resize(self, cols: int, rows: int) -> None:
        """Resize the terminal."""
        if self._state != SessionState.RUNNING:
            return

        self._run_tmux(
            "resize-window", "-t", self._id, "-x", str(cols), "-y", str(rows),
            check=False
        )

    def on_output(self, callback: Callable[[ExtractedOutput], None]) -> None:
        """Register output callback."""
        self._output_callbacks.append(callback)

    def on_state_change(
        self, callback: Callable[[SessionState, SessionState], None]
    ) -> None:
        """Register state change callback."""
        self._state_callbacks.append(callback)

    def start_polling(self) -> None:
        """Start polling for output changes."""
        if self._polling_thread and self._polling_thread.is_alive():
            return

        self._stop_polling.clear()
        poll_interval = self._config.timing.poll_interval

        def poll_loop():
            last_output = ""
            while not self._stop_polling.is_set():
                if self._state != SessionState.RUNNING:
                    break
                try:
                    output = self.extract()
                    if output.text != last_output:
                        last_output = output.text
                        for cb in self._output_callbacks:
                            cb(output)
                except Exception:
                    pass
                time.sleep(poll_interval)

        self._polling_thread = threading.Thread(target=poll_loop, daemon=True)
        self._polling_thread.start()

    def stop_polling(self) -> None:
        """Stop polling for output."""
        self._stop_polling.set()


# Verify it implements the protocol
def _check_protocol() -> None:
    """Verify TmuxSession implements Session protocol."""
    session: Session = TmuxSession()  # noqa: F841


_check_protocol()

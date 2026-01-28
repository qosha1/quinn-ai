"""
TmuxSession - Session implementation using tmux.

Uses subprocess calls to tmux for session management.
"""

import logging
import shlex
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

logger = logging.getLogger(__name__)

# Timeout for tmux subprocess operations (in seconds)
TMUX_TIMEOUT = 5


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

    @classmethod
    def exists(cls, session_name: str) -> bool:
        """Check if a tmux session with the given name exists.

        Class method for checking external sessions.

        Args:
            session_name: tmux session name to check

        Returns:
            True if session exists
        """
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True,
                text=True,
                timeout=TMUX_TIMEOUT,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False

    @classmethod
    def connect(cls, session_name: str, config: PytermConfig | None = None) -> "TmuxSession":
        """Connect to an existing tmux session.

        Factory method that creates a TmuxSession instance connected
        to an existing external session. The session must already exist.

        Args:
            session_name: Name of existing tmux session
            config: Optional pyterm configuration

        Returns:
            TmuxSession instance connected to the session

        Raises:
            ValueError: If session does not exist
        """
        if not cls.exists(session_name):
            raise ValueError(f"Tmux session '{session_name}' does not exist")

        session = cls(session_name=session_name, config=config)
        session._state = SessionState.RUNNING

        # Try to get PID of the existing session
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-t", session_name, "-p", "#{pane_pid}"],
                capture_output=True,
                text=True,
                timeout=TMUX_TIMEOUT,
            )
            if result.returncode == 0 and result.stdout.strip():
                session._pid = int(result.stdout.strip())
        except (ValueError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass  # PID extraction is optional

        return session

    @classmethod
    def capture(cls, session_name: str) -> str:
        """Capture pane output from a tmux session.

        Class method for capturing output from any session.

        Args:
            session_name: tmux session name

        Returns:
            Current pane content, or empty string if capture fails
        """
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p"],
                capture_output=True,
                text=True,
                timeout=TMUX_TIMEOUT,
            )
            return result.stdout if result.returncode == 0 else ""
        except subprocess.TimeoutExpired:
            return ""

    @classmethod
    def attach(cls, session_name: str) -> None:
        """Attach to a tmux session, replacing the current process.

        This uses os.execvp so it does not return - the current
        process is replaced by tmux.

        Args:
            session_name: tmux session name to attach to
        """
        import os
        os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])

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
        """Run a tmux command with timeout."""
        cmd = ["tmux"] + list(args)
        return subprocess.run(
            cmd, capture_output=True, text=True, check=check, timeout=TMUX_TIMEOUT
        )

    def _session_exists(self) -> bool:
        """Check if tmux session exists."""
        result = self._run_tmux("has-session", "-t", self._id, check=False)
        return result.returncode == 0

    def start(self, config: SessionConfig | None = None) -> None:
        """Start the tmux session.

        Creates a tmux session with bash as the shell, then sends the command
        (if provided) via send-keys. This ensures commands execute properly
        rather than being interpreted as the shell itself.
        """
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
        # ALWAYS use bash as shell - never pass commands as the shell argument
        cmd_args = [
            "new-session",
            "-d",  # detached
            "-s", self._id,  # session name
            "-x", str(self._session_config.cols),
            "-y", str(self._session_config.rows),
        ]

        if self._session_config.cwd:
            cmd_args.extend(["-c", self._session_config.cwd])

        # Always use bash as the shell (tmux interprets last arg as shell)
        cmd_args.append("/bin/bash")

        # Create the tmux session with bash
        self._run_tmux(*cmd_args)

        # Set environment variables AFTER session is created
        for key, value in self._session_config.env.items():
            self._run_tmux("set-environment", "-t", self._id, key, value)

        # Determine if we need to execute a command
        # List of known real shells - if shell is not in this list, treat it as a command
        real_shells = ["/bin/bash", "/bin/zsh", "/bin/sh", "bash", "zsh", "sh"]

        if self._session_config.shell not in real_shells:
            # Shell field contains a command to execute (like "claude")
            command = self._session_config.shell
            if self._session_config.args:
                # Use shlex.join for proper escaping of arguments
                command = f"{command} {shlex.join(self._session_config.args)}"

            logger.info(f"Executing command in tmux session {self._id}: {command}")

            # Send command to bash running in tmux
            self._run_tmux("send-keys", "-t", self._id, command, "Enter")

            # Brief wait for process to start
            time.sleep(0.5)

        # Get the pane PID
        result = self._run_tmux(
            "display-message", "-t", self._id, "-p", "#{pane_pid}"
        )
        bash_pid = int(result.stdout.strip()) if result.stdout.strip() else None

        # Try to find child process of bash (this is our command)
        if bash_pid and self._session_config.shell not in real_shells:
            try:
                # Use ps to find children of bash_pid
                # macOS compatible: ps -o pid,ppid then filter
                ps_result = subprocess.run(
                    ["ps", "-o", "pid,ppid"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if ps_result.returncode == 0:
                    # Parse output to find processes with PPID matching bash_pid
                    child_pid = None
                    for line in ps_result.stdout.splitlines()[1:]:  # Skip header
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            pid, ppid = parts[0], parts[1]
                            if ppid == str(bash_pid):
                                child_pid = int(pid)
                                break

                    if child_pid:
                        self._pid = child_pid
                        logger.info(f"Found command process PID: {self._pid}")
                    else:
                        # No child process yet, command may not have started
                        logger.info(f"No child process found for bash PID {bash_pid}, using bash PID")
                        self._pid = bash_pid
                else:
                    logger.warning(f"ps command failed, using bash PID {bash_pid}")
                    self._pid = bash_pid
            except (subprocess.SubprocessError, ValueError) as e:
                logger.warning(f"Failed to get child PID: {e}, using bash PID {bash_pid}")
                self._pid = bash_pid
        else:
            # Just running bash, use bash PID
            self._pid = bash_pid

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
                        # Copy callbacks to avoid modification during iteration
                        callbacks = list(self._output_callbacks)
                        for cb in callbacks:
                            try:
                                cb(output)
                            except Exception as e:
                                logger.warning(f"Output callback failed: {e}")
                except Exception as e:
                    logger.debug(f"Poll loop error: {e}")
                time.sleep(poll_interval)

        self._polling_thread = threading.Thread(target=poll_loop, daemon=True)
        self._polling_thread.start()

    def stop_polling(self) -> None:
        """Stop polling for output and wait for thread to exit."""
        self._stop_polling.set()
        if self._polling_thread and self._polling_thread.is_alive():
            self._polling_thread.join(timeout=2.0)
            if self._polling_thread.is_alive():
                logger.warning("Polling thread did not exit cleanly")


# Verify it implements the protocol
def _check_protocol() -> None:
    """Verify TmuxSession implements Session protocol."""
    session: Session = TmuxSession()  # noqa: F841


_check_protocol()

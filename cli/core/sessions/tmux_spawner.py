"""
TmuxSpawner - Tmux-based session spawning strategy.

Spawns sessions inside tmux for:
- Persistence across process restarts
- Reattachment capability
- Better terminal emulation
- Log capture to files

Best for:
- Production deployments
- Long-running sessions
- Sessions that need to survive parent process restart
"""

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .spawner import (
    SpawnStrategy,
    SpawnerConfig,
    SpawnResult,
    SpawnError,
    SessionNotFoundError,
    SpawnFailedError,
)
from ..constants import TMUX_SESSION_PREFIX


class TmuxSpawner(SpawnStrategy):
    """Spawn sessions inside tmux.

    Each session runs in a dedicated tmux session, allowing:
    - Persistence: sessions survive parent process death
    - Reattach: can reconnect to running sessions
    - Logging: output captured to files
    """

    def __init__(self, socket_path: Optional[Path] = None):
        """Initialize tmux spawner.

        Args:
            socket_path: Optional custom tmux socket path
        """
        self._socket_path = socket_path
        self._tmux_cmd = self._find_tmux()

    @property
    def name(self) -> str:
        """Strategy name."""
        return "tmux"

    def _find_tmux(self) -> Optional[str]:
        """Find tmux binary."""
        return shutil.which("tmux")

    def _run_tmux(self, *args, capture: bool = True) -> subprocess.CompletedProcess:
        """Run a tmux command.

        Args:
            *args: Tmux subcommand and arguments
            capture: Whether to capture output

        Returns:
            CompletedProcess result
        """
        if not self._tmux_cmd:
            raise SpawnFailedError(self.name, "tmux not found in PATH")

        cmd = [self._tmux_cmd]
        if self._socket_path:
            cmd.extend(["-S", str(self._socket_path)])
        cmd.extend(args)

        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=10,
        )

    def spawn(self, config: SpawnerConfig) -> SpawnResult:
        """Spawn a tmux session.

        Args:
            config: Spawner configuration

        Returns:
            SpawnResult with tmux session name as session_id
        """
        if not self._tmux_cmd:
            return SpawnResult(
                success=False,
                error="tmux not found in PATH",
            )

        # Generate session name
        session_name = config.session_name or f"{TMUX_SESSION_PREFIX}{config.worker_id or 'session'}"

        try:
            # Check if session already exists
            result = self._run_tmux("has-session", "-t", session_name)
            if result.returncode == 0:
                return SpawnResult(
                    success=False,
                    error=f"Session already exists: {session_name}",
                )

            # Build command string for tmux (use shlex.quote for safe escaping)
            if config.args:
                cmd_str = config.command + " " + " ".join(shlex.quote(arg) for arg in config.args)
            else:
                cmd_str = config.command

            # Build tmux new-session command
            tmux_args = [
                "new-session",
                "-d",  # Detached
                "-s", session_name,
                "-x", str(config.cols),
                "-y", str(config.rows),
            ]

            # Set working directory
            if config.working_directory:
                tmux_args.extend(["-c", str(config.working_directory)])

            # Set environment variables for the spawned process via
            # `tmux new-session -e KEY=VALUE`. The previous implementation
            # used `set-environment` BEFORE create which silently no-op'd
            # because the session didn't exist yet (bug quinn-ai-ad8).
            for key, value in config.env_vars.items():
                tmux_args.extend(["-e", f"{key}={value}"])

            # Add the command
            tmux_args.append(cmd_str)

            # Create session
            result = self._run_tmux(*tmux_args)

            if result.returncode != 0:
                return SpawnResult(
                    success=False,
                    error=f"tmux new-session failed: {result.stderr}",
                )

            # Get the PID of the process in the session
            pid = self._get_session_pid(session_name)

            return SpawnResult(
                success=True,
                pid=pid,
                session_id=session_name,
                metadata={
                    "strategy": self.name,
                    "session_name": session_name,
                    "command": config.command,
                },
            )

        except subprocess.TimeoutExpired:
            return SpawnResult(
                success=False,
                error="tmux command timed out",
            )
        except (OSError, subprocess.SubprocessError) as e:
            # OSError: file/process issues, SubprocessError: tmux command failed
            return SpawnResult(
                success=False,
                error=str(e),
            )

    def _get_session_pid(self, session_name: str) -> Optional[int]:
        """Get PID of the main process in a tmux session."""
        try:
            result = self._run_tmux(
                "list-panes",
                "-t", session_name,
                "-F", "#{pane_pid}",
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split("\n")[0])
        except (OSError, ValueError, subprocess.SubprocessError):
            # OSError: process issues, ValueError: invalid PID format
            # SubprocessError: tmux command failed
            pass
        return None

    def stop(self, session_id: str, force: bool = False) -> bool:
        """Stop a tmux session.

        Only stops sessions whose name starts with the QuinnAI prefix to avoid
        accidentally killing unrelated sessions (e.g., the board's own session).

        Args:
            session_id: Tmux session name
            force: If True, kill immediately without cleanup

        Returns:
            True if session was stopped
        """
        if not session_id.startswith(TMUX_SESSION_PREFIX):
            return False

        try:
            if not force:
                # Try graceful shutdown first - send Ctrl+C
                self._run_tmux("send-keys", "-t", session_id, "C-c")
                # Wait a bit
                import time
                time.sleep(0.5)

            # Kill the session
            result = self._run_tmux("kill-session", "-t", session_id)
            return result.returncode == 0

        except (OSError, subprocess.SubprocessError):
            # OSError: process issues, SubprocessError: tmux command failed
            return False

    def is_alive(self, session_id: str) -> bool:
        """Check if tmux session exists and is running.

        Args:
            session_id: Tmux session name

        Returns:
            True if session exists
        """
        try:
            result = self._run_tmux("has-session", "-t", session_id)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            # OSError: process issues, SubprocessError: tmux command failed
            return False

    def send_input(self, session_id: str, text: str) -> bool:
        """Send input to tmux session.

        Args:
            session_id: Tmux session name
            text: Text to send

        Returns:
            True if input was sent
        """
        try:
            # Use send-keys to send the text
            result = self._run_tmux("send-keys", "-t", session_id, text)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            # OSError: process issues, SubprocessError: tmux command failed
            return False

    def read_output(self, session_id: str, timeout_ms: Optional[int] = None) -> str:
        """Read output from tmux session.

        Uses capture-pane to get current pane content.

        Args:
            session_id: Tmux session name
            timeout_ms: Ignored for tmux (capture is instant)

        Returns:
            Output text
        """
        try:
            result = self._run_tmux(
                "capture-pane",
                "-t", session_id,
                "-p",  # Print to stdout
                "-S", "-1000",  # Start from 1000 lines back
            )
            if result.returncode == 0:
                return result.stdout
            return ""
        except (OSError, subprocess.SubprocessError):
            # OSError: process issues, SubprocessError: tmux command failed
            return ""

    def attach(self, session_id: str) -> bool:
        """Attach to tmux session for interactive debugging.

        This will take over the terminal.

        Args:
            session_id: Tmux session name

        Returns:
            True if attachment succeeded
        """
        if not self._tmux_cmd:
            return False

        try:
            cmd = [self._tmux_cmd]
            if self._socket_path:
                cmd.extend(["-S", str(self._socket_path)])
            cmd.extend(["attach-session", "-t", session_id])

            # Run attach (this blocks and takes over terminal)
            subprocess.run(cmd, check=True)
            return True
        except (OSError, subprocess.SubprocessError):
            # OSError: process issues, SubprocessError: tmux/subprocess failed
            return False

    def send_signal(self, session_id: str, sig: int) -> bool:
        """Send signal to process in tmux session.

        Args:
            session_id: Tmux session name
            sig: Signal number

        Returns:
            True if signal was sent
        """
        pid = self._get_session_pid(session_id)
        if pid:
            try:
                os.kill(pid, sig)
                return True
            except OSError:
                # Process may have exited, permissions issue, or invalid signal
                pass
        return False

    def list_sessions(self) -> list[str]:
        """List all tmux sessions.

        Returns:
            List of session names
        """
        try:
            result = self._run_tmux("list-sessions", "-F", "#{session_name}")
            if result.returncode == 0:
                return [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
        except (OSError, subprocess.SubprocessError):
            # OSError: process issues, SubprocessError: tmux command failed
            pass
        return []

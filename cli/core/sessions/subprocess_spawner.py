"""
SubprocessSpawner - Direct subprocess spawning strategy.

Simple, ephemeral spawning using Python's subprocess module.
Sessions don't persist across process restarts.

Best for:
- Development/testing
- Short-lived sessions
- Environments without tmux
"""

import os
import signal
import subprocess
import threading
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


class SubprocessSpawner(SpawnStrategy):
    """Spawn sessions as direct subprocesses.

    Uses subprocess.Popen for simple, synchronous spawning.
    Sessions are ephemeral - they don't persist if the parent
    process dies.

    Thread-safe: Uses a lock to protect the process dictionary.
    """

    def __init__(self):
        """Initialize subprocess spawner."""
        # Track running processes by session ID (pid as string)
        self._processes: dict[str, subprocess.Popen] = {}
        # Lock for thread-safe access to _processes
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        """Strategy name."""
        return "subprocess"

    def spawn(self, config: SpawnerConfig) -> SpawnResult:
        """Spawn a subprocess.

        Args:
            config: Spawner configuration

        Returns:
            SpawnResult with PID as session_id
        """
        try:
            # Build command
            cmd = [config.command] + config.args

            # Build environment
            env = os.environ.copy()
            env.update(config.env_vars)

            # Working directory
            cwd = str(config.working_directory) if config.working_directory else None

            # Spawn process
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=cwd,
                bufsize=0,  # Unbuffered
            )

            # Use PID as session ID
            session_id = str(process.pid)
            with self._lock:
                self._processes[session_id] = process

            return SpawnResult(
                success=True,
                pid=process.pid,
                session_id=session_id,
                metadata={
                    "strategy": self.name,
                    "command": config.command,
                    "args": config.args,
                },
            )

        except FileNotFoundError:
            return SpawnResult(
                success=False,
                error=f"Command not found: {config.command}",
            )
        except PermissionError:
            return SpawnResult(
                success=False,
                error=f"Permission denied: {config.command}",
            )
        except (OSError, subprocess.SubprocessError) as e:
            # OSError: file/process issues, SubprocessError: spawn failed
            return SpawnResult(
                success=False,
                error=str(e),
            )

    def stop(self, session_id: str, force: bool = False) -> bool:
        """Stop a subprocess.

        Args:
            session_id: PID as string
            force: If True, use SIGKILL instead of SIGTERM

        Returns:
            True if process was stopped
        """
        with self._lock:
            process = self._processes.get(session_id)
            if not process:
                return False

        try:
            if force:
                process.kill()  # SIGKILL
            else:
                process.terminate()  # SIGTERM

            # Wait for process to exit (with timeout)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if didn't exit
                process.kill()
                process.wait(timeout=2)

            with self._lock:
                self._processes.pop(session_id, None)
            return True

        except OSError:
            # Process may have exited, permissions issue, or other OS error
            return False

    def is_alive(self, session_id: str) -> bool:
        """Check if subprocess is running.

        Args:
            session_id: PID as string

        Returns:
            True if process is alive
        """
        with self._lock:
            process = self._processes.get(session_id)
            if not process:
                return False

        alive = process.poll() is None
        # Clean up dead process from tracking
        if not alive:
            with self._lock:
                self._processes.pop(session_id, None)
        return alive

    def send_input(self, session_id: str, text: str) -> bool:
        """Send input to subprocess stdin.

        Args:
            session_id: PID as string
            text: Text to send

        Returns:
            True if input was sent
        """
        with self._lock:
            process = self._processes.get(session_id)
            if not process or process.stdin is None:
                return False

        try:
            process.stdin.write(text.encode())
            process.stdin.flush()
            return True
        except (OSError, IOError):
            # OSError: broken pipe, process exited; IOError: stdin closed
            return False

    def read_output(self, session_id: str, timeout_ms: Optional[int] = None) -> str:
        """Read output from subprocess stdout.

        Args:
            session_id: PID as string
            timeout_ms: Optional timeout in milliseconds

        Returns:
            Output text
        """
        with self._lock:
            process = self._processes.get(session_id)
            if not process or process.stdout is None:
                return ""

        try:
            # Read available bytes without blocking
            import select

            # Use select to check if data is available
            # Convert timeout_ms to seconds, default to 0.1
            timeout_sec = (timeout_ms / 1000.0) if timeout_ms else 0.1
            if hasattr(select, 'select'):
                readable, _, _ = select.select([process.stdout], [], [], timeout_sec)
                if readable:
                    return process.stdout.read(4096).decode('utf-8', errors='replace')
            return ""
        except (OSError, IOError, ValueError):
            # OSError: broken pipe; IOError: stdout closed; ValueError: I/O on closed file
            return ""

    def send_signal(self, session_id: str, sig: int) -> bool:
        """Send signal to subprocess.

        Args:
            session_id: PID as string
            sig: Signal number

        Returns:
            True if signal was sent
        """
        with self._lock:
            process = self._processes.get(session_id)
            if not process:
                return False

        try:
            process.send_signal(sig)
            return True
        except OSError:
            # Process may have exited, permissions issue, or invalid signal
            return False

    def cleanup(self) -> None:
        """Clean up all tracked processes."""
        with self._lock:
            session_ids = list(self._processes.keys())
        for session_id in session_ids:
            self.stop(session_id, force=True)

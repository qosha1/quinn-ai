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
    """

    def __init__(self):
        """Initialize subprocess spawner."""
        # Track running processes by session ID (pid as string)
        self._processes: dict[str, subprocess.Popen] = {}

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
        except Exception as e:
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

            del self._processes[session_id]
            return True

        except Exception:
            return False

    def is_alive(self, session_id: str) -> bool:
        """Check if subprocess is running.

        Args:
            session_id: PID as string

        Returns:
            True if process is alive
        """
        process = self._processes.get(session_id)
        if not process:
            return False

        return process.poll() is None

    def send_input(self, session_id: str, text: str) -> bool:
        """Send input to subprocess stdin.

        Args:
            session_id: PID as string
            text: Text to send

        Returns:
            True if input was sent
        """
        process = self._processes.get(session_id)
        if not process or process.stdin is None:
            return False

        try:
            process.stdin.write(text.encode())
            process.stdin.flush()
            return True
        except Exception:
            return False

    def read_output(self, session_id: str, timeout_ms: Optional[int] = None) -> str:
        """Read output from subprocess stdout.

        Args:
            session_id: PID as string
            timeout_ms: Optional timeout (note: basic implementation ignores this)

        Returns:
            Output text
        """
        process = self._processes.get(session_id)
        if not process or process.stdout is None:
            return ""

        try:
            # Read available bytes without blocking
            import select

            # Use select to check if data is available
            if hasattr(select, 'select'):
                readable, _, _ = select.select([process.stdout], [], [], 0.1)
                if readable:
                    return process.stdout.read(4096).decode('utf-8', errors='replace')
            return ""
        except Exception:
            return ""

    def send_signal(self, session_id: str, sig: int) -> bool:
        """Send signal to subprocess.

        Args:
            session_id: PID as string
            sig: Signal number

        Returns:
            True if signal was sent
        """
        process = self._processes.get(session_id)
        if not process:
            return False

        try:
            process.send_signal(sig)
            return True
        except Exception:
            return False

    def cleanup(self) -> None:
        """Clean up all tracked processes."""
        for session_id in list(self._processes.keys()):
            self.stop(session_id, force=True)

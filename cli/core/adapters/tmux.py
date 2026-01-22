"""
Tmux adapter for terminal multiplexer operations.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .process import ProcessAdapter, ProcessResult, SubprocessAdapter


@dataclass
class TmuxSession:
    """Information about a tmux session."""
    name: str
    created: Optional[str] = None
    attached: bool = False


class TmuxAdapter:
    """Adapter for tmux operations."""

    def __init__(self, process: Optional[ProcessAdapter] = None):
        self._process = process or SubprocessAdapter()

    def has_session(self, name: str) -> bool:
        """Check if a tmux session exists."""
        result = self._process.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True,
        )
        return result.success

    def list_sessions(self) -> list[TmuxSession]:
        """List all tmux sessions."""
        result = self._process.run(
            ["tmux", "list-sessions", "-F", "#{session_name}:#{session_created}:#{session_attached}"],
            capture_output=True,
        )
        if not result.success:
            return []

        sessions = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                sessions.append(TmuxSession(
                    name=parts[0],
                    created=parts[1] if parts[1] else None,
                    attached=parts[2] == "1",
                ))
        return sessions

    def capture_pane(
        self,
        session_name: str,
        lines: int = 1000,
        start_line: Optional[int] = None,
    ) -> Optional[str]:
        """Capture output from a tmux pane."""
        cmd = ["tmux", "capture-pane", "-t", session_name, "-p"]
        if start_line is not None:
            cmd.extend(["-S", str(start_line)])
        cmd.extend(["-E", str(lines)])

        result = self._process.run(cmd, capture_output=True)
        return result.stdout if result.success else None

    def send_keys(self, session_name: str, keys: str, enter: bool = True) -> bool:
        """Send keys to a tmux session."""
        cmd = ["tmux", "send-keys", "-t", session_name, keys]
        if enter:
            cmd.append("Enter")
        result = self._process.run(cmd)
        return result.success

    def kill_session(self, session_name: str) -> bool:
        """Kill a tmux session."""
        result = self._process.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
        )
        return result.success

    def new_session(
        self,
        name: str,
        command: Optional[str] = None,
        cwd: Optional[Path] = None,
        detached: bool = True,
    ) -> bool:
        """Create a new tmux session."""
        cmd = ["tmux", "new-session", "-s", name]
        if detached:
            cmd.append("-d")
        if cwd:
            cmd.extend(["-c", str(cwd)])
        if command:
            cmd.append(command)

        result = self._process.run(cmd)
        return result.success

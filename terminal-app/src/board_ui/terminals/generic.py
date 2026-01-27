"""
Generic terminal provider (fallback).

Uses x-terminal-emulator on Linux or falls back to spawning
a basic terminal. This is the last resort when no specific
terminal provider is available.
"""

import os
import platform
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from ..interfaces.terminal import TerminalProvider, TerminalType, WindowHandle
from .registry import register_provider


def _escape_applescript(text: str) -> str:
    """Escape a string for safe use in AppleScript.

    Escapes backslashes first, then quotes to prevent injection.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


# Timeout for subprocess operations (in seconds)
SUBPROCESS_TIMEOUT = 5


class GenericTerminal(TerminalProvider):
    """Fallback terminal provider using system defaults.

    On Linux: Uses x-terminal-emulator if available
    On macOS: Falls back to open -a Terminal (always available)
    On Windows: Uses start cmd

    This is less elegant than specific providers but ensures
    the board UI works everywhere.
    """

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.GENERIC

    def is_available(self) -> bool:
        """Generic provider is always available as fallback."""
        return True

    def _get_terminal_command(self) -> list[str]:
        """Get the command to spawn a terminal on this system."""
        system = platform.system()

        if system == "Linux":
            # Try common Linux terminal emulators
            for term in ["x-terminal-emulator", "gnome-terminal", "konsole", "xterm"]:
                if shutil.which(term):
                    return [term]
            return ["xterm"]  # Last resort

        elif system == "Darwin":
            return ["open", "-a", "Terminal"]

        elif system == "Windows":
            return ["cmd", "/c", "start", "cmd"]

        return ["xterm"]

    def _validate_tmux_session(self, session_name: str) -> bool:
        """Check if a tmux session exists and is valid.

        Args:
            session_name: Name of the tmux session to validate

        Returns:
            True if session exists and is valid, False otherwise
        """
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True,
                timeout=2,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def open_window(
        self,
        title: str,
        command: str,
        working_directory: Optional[Path] = None,
    ) -> WindowHandle:
        """Open a new terminal window running the command."""
        window_id = str(uuid.uuid4())[:8]
        system = platform.system()

        if system == "Linux":
            # Most Linux terminals support -e for command
            # Use shlex.join for safe command construction
            term = self._get_terminal_command()[0]
            if term == "gnome-terminal":
                cmd = [term, "--title", title, "--", "sh", "-c", command]
            else:
                # Use list form with sh -c to avoid shell injection
                cmd = [term, "-e", "sh", "-c", command]

        elif system == "Darwin":
            # Use osascript for macOS with proper escaping
            escaped_cmd = _escape_applescript(command)
            script = f'tell application "Terminal" to do script "{escaped_cmd}"'
            try:
                subprocess.run(
                    ["osascript", "-e", script],
                    check=False,
                    capture_output=True,
                    timeout=SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                pass  # Best effort - window may have opened anyway
            return WindowHandle(
                window_id=window_id,
                terminal_type=self.terminal_type,
                title=title,
            )

        elif system == "Windows":
            # Windows cmd - command is passed as argument, less injection risk
            cmd = ["cmd", "/c", "start", "cmd", "/k", command]

        else:
            cmd = ["xterm", "-e", "sh", "-c", command]

        # Set working directory via environment
        env = os.environ.copy()
        cwd = str(working_directory) if working_directory else None

        subprocess.Popen(cmd, cwd=cwd, env=env)

        return WindowHandle(
            window_id=window_id,
            terminal_type=self.terminal_type,
            title=title,
        )

    def attach_to_session(
        self,
        title: str,
        session_name: str,
    ) -> WindowHandle:
        """Open a terminal attached to a tmux session."""
        # Validate session exists before attempting attach
        if not self._validate_tmux_session(session_name):
            raise ValueError(
                f"tmux session '{session_name}' not found or invalid. "
                "Session may have died or been killed. "
                "Try restarting the worker session."
            )

        # Use shlex.quote to prevent shell injection in session name
        tmux_cmd = f"tmux attach-session -t {shlex.quote(session_name)}"
        return self.open_window(title, tmux_cmd)


# Register this provider (lowest priority)
register_provider(TerminalType.GENERIC, GenericTerminal)

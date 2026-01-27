"""
iTerm2 terminal provider.

Uses AppleScript to control iTerm2 on macOS.
"""

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


class ITermTerminal(TerminalProvider):
    """Terminal provider for iTerm2 on macOS.

    Uses AppleScript for window control.
    """

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.ITERM2

    def is_available(self) -> bool:
        """Check if iTerm2 is installed (macOS only)."""
        if platform.system() != "Darwin":
            return False

        # Check if iTerm2 app exists
        iterm_paths = [
            Path("/Applications/iTerm.app"),
            Path.home() / "Applications/iTerm.app",
        ]

        return any(p.exists() for p in iterm_paths)

    def _run_applescript(self, script: str) -> bool:
        """Run an AppleScript and return success status."""
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

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
        """Open a new iTerm2 window running the command."""
        window_id = str(uuid.uuid4())[:8]

        # Build the command with optional cd (use shlex.quote for shell safety)
        if working_directory:
            full_command = f"cd {shlex.quote(str(working_directory))} && {command}"
        else:
            full_command = command

        # Escape for AppleScript injection safety
        escaped_title = _escape_applescript(title)
        escaped_cmd = _escape_applescript(full_command)

        # AppleScript to create new window with command
        script = f'''
        tell application "iTerm2"
            activate
            set newWindow to (create window with default profile)
            tell current session of newWindow
                set name to "{escaped_title}"
                write text "{escaped_cmd}"
            end tell
        end tell
        '''

        self._run_applescript(script)

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
        """Open an iTerm2 window attached to a tmux session."""
        window_id = str(uuid.uuid4())[:8]

        # Validate session exists before attempting attach
        if not self._validate_tmux_session(session_name):
            raise ValueError(
                f"tmux session '{session_name}' not found or invalid. "
                "Session may have died or been killed. "
                "Try restarting the worker session."
            )

        # Use shlex.quote to prevent shell injection in session name
        tmux_cmd = f"tmux attach-session -t {shlex.quote(session_name)}"

        # Escape for AppleScript injection safety
        escaped_title = _escape_applescript(title)
        escaped_cmd = _escape_applescript(tmux_cmd)

        script = f'''
        tell application "iTerm2"
            activate
            set newWindow to (create window with default profile)
            tell current session of newWindow
                set name to "{escaped_title}"
                write text "{escaped_cmd}"
            end tell
        end tell
        '''

        self._run_applescript(script)

        return WindowHandle(
            window_id=window_id,
            terminal_type=self.terminal_type,
            title=title,
            session_name=session_name,
        )


# Register this provider
register_provider(TerminalType.ITERM2, ITermTerminal)

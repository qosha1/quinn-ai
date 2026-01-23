"""
macOS Terminal.app provider.

Uses AppleScript to control the built-in Terminal app.
"""

import platform
import shlex
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


class MacOSTerminal(TerminalProvider):
    """Terminal provider for macOS Terminal.app.

    Uses AppleScript for window control. Always available on macOS.
    """

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.MACOS_TERMINAL

    def is_available(self) -> bool:
        """Check if running on macOS (Terminal.app always available)."""
        return platform.system() == "Darwin"

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

    def open_window(
        self,
        title: str,
        command: str,
        working_directory: Optional[Path] = None,
    ) -> WindowHandle:
        """Open a new Terminal.app window running the command."""
        window_id = str(uuid.uuid4())[:8]

        # Build the command with optional cd (use shlex.quote for shell safety)
        if working_directory:
            full_command = f"cd {shlex.quote(str(working_directory))} && {command}"
        else:
            full_command = command

        # Escape for AppleScript injection safety (backslash first, then quotes)
        escaped_cmd = _escape_applescript(full_command)
        escaped_title = _escape_applescript(title)

        script = f'''
        tell application "Terminal"
            activate
            do script "{escaped_cmd}"
            set custom title of front window to "{escaped_title}"
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
        """Open a Terminal.app window attached to a tmux session."""
        window_id = str(uuid.uuid4())[:8]

        # Use shlex.quote to prevent shell injection in session name
        tmux_cmd = f"tmux attach-session -t {shlex.quote(session_name)}"

        # Escape for AppleScript injection safety
        escaped_cmd = _escape_applescript(tmux_cmd)
        escaped_title = _escape_applescript(title)

        script = f'''
        tell application "Terminal"
            activate
            do script "{escaped_cmd}"
            set custom title of front window to "{escaped_title}"
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
register_provider(TerminalType.MACOS_TERMINAL, MacOSTerminal)

"""
macOS Terminal.app provider.

Uses AppleScript to control the built-in Terminal app.
"""

import platform
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from ..interfaces.terminal import TerminalProvider, TerminalType, WindowHandle
from .registry import register_provider


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
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def open_window(
        self,
        title: str,
        command: str,
        working_directory: Optional[Path] = None,
    ) -> WindowHandle:
        """Open a new Terminal.app window running the command."""
        window_id = str(uuid.uuid4())[:8]

        # Build the command with optional cd
        full_command = command
        if working_directory:
            full_command = f"cd {working_directory} && {command}"

        # Escape quotes for AppleScript
        escaped_cmd = full_command.replace('"', '\\"')
        escaped_title = title.replace('"', '\\"')

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

        tmux_cmd = f"tmux attach-session -t {session_name}"
        escaped_title = title.replace('"', '\\"')

        script = f'''
        tell application "Terminal"
            activate
            do script "{tmux_cmd}"
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

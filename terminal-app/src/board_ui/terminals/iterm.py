"""
iTerm2 terminal provider.

Uses AppleScript to control iTerm2 on macOS.
"""

import platform
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from ..interfaces.terminal import TerminalProvider, TerminalType, WindowHandle
from .registry import register_provider


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
        """Open a new iTerm2 window running the command."""
        window_id = str(uuid.uuid4())[:8]

        # Build the command with optional cd
        full_command = command
        if working_directory:
            full_command = f"cd {working_directory} && {command}"

        # AppleScript to create new window with command
        script = f'''
        tell application "iTerm2"
            activate
            set newWindow to (create window with default profile)
            tell current session of newWindow
                set name to "{title}"
                write text "{full_command}"
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

        tmux_cmd = f"tmux attach-session -t {session_name}"

        script = f'''
        tell application "iTerm2"
            activate
            set newWindow to (create window with default profile)
            tell current session of newWindow
                set name to "{title}"
                write text "{tmux_cmd}"
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

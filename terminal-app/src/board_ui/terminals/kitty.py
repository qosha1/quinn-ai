"""
Kitty terminal provider.

Kitty has excellent remote control capabilities via `kitty @` commands.
This allows us to spawn new windows with specific titles and commands.
"""

import shlex
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from ..interfaces.terminal import TerminalProvider, TerminalType, WindowHandle
from .registry import register_provider

# Timeout for subprocess operations (in seconds)
SUBPROCESS_TIMEOUT = 5


class KittyTerminal(TerminalProvider):
    """Terminal provider for Kitty terminal emulator.

    Uses Kitty's remote control protocol to spawn new OS windows.
    Requires allow_remote_control=yes in kitty.conf.
    """

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.KITTY

    def is_available(self) -> bool:
        """Check if Kitty is installed and remote control is available."""
        # Check if kitty binary exists
        if shutil.which("kitty") is None:
            return False

        # Check if we can use remote control
        # This will fail if Kitty isn't running or remote control is disabled
        try:
            result = subprocess.run(
                ["kitty", "@", "ls"],
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
        """Open a new Kitty OS window running the command."""
        window_id = str(uuid.uuid4())[:8]

        cmd = [
            "kitty", "@", "launch",
            "--type=os-window",
            f"--title={title}",
        ]

        if working_directory:
            cmd.append(f"--cwd={working_directory}")

        # Add the command to run
        cmd.extend(["--", "sh", "-c", command])

        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to open Kitty window: {e.stderr.decode() if e.stderr else str(e)}"
            ) from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("Kitty command timed out") from None

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
        """Open a Kitty window attached to a tmux session.

        When the user closes this window, it just detaches from tmux.
        The tmux session (and worker) keeps running.
        """
        window_id = str(uuid.uuid4())[:8]

        # tmux attach-session -t <session> will attach if exists
        # If window is closed, tmux just detaches - session keeps running
        # Use shlex.quote to prevent shell injection in session name
        tmux_cmd = f"tmux attach-session -t {shlex.quote(session_name)}"

        cmd = [
            "kitty", "@", "launch",
            "--type=os-window",
            f"--title={title}",
            "--",
            "sh", "-c", tmux_cmd,
        ]

        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to attach to tmux session: {e.stderr.decode() if e.stderr else str(e)}"
            ) from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("Kitty command timed out") from None

        return WindowHandle(
            window_id=window_id,
            terminal_type=self.terminal_type,
            title=title,
            session_name=session_name,
        )


# Register this provider
register_provider(TerminalType.KITTY, KittyTerminal)

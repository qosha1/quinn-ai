"""
Tmux link-window terminal provider.

Links worker windows into the board's tmux session using tmux link-window.
No nesting — both sessions share the same underlying window pane.

This is the correct approach for ttyd/browser viewers: the linked window
appears as a new tmux window in the board session, visible to anyone
viewing that session (via ttyd, kitty attach, or any terminal).
"""

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from ..interfaces.terminal import TerminalProvider, TerminalType, WindowHandle
from .registry import register_provider

SUBPROCESS_TIMEOUT = 5


class TmuxLinkProvider(TerminalProvider):
    """Links worker windows into the board's tmux session.

    Uses tmux link-window to share the worker's terminal pane into
    the board session. The worker's session and the board session both
    point to the same window — zero nesting, zero extra tmux clients.

    Works for all viewers: Kitty attach, ttyd/browser, any terminal.
    """

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.TMUX_LINK

    def _get_current_tmux_session(self) -> Optional[str]:
        """Get the tmux session name we're currently running inside."""
        tmux_env = os.environ.get("TMUX")
        if not tmux_env:
            return None

        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{session_name}"],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def is_available(self) -> bool:
        """Available if we're running inside a tmux session."""
        if os.environ.get("TMUX") is None:
            return False

        if shutil.which("tmux") is None:
            return False

        return self._get_current_tmux_session() is not None

    def _validate_tmux_session(self, session_name: str) -> bool:
        """Check if a tmux session exists."""
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _run_tmux(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run a tmux command."""
        cmd = ["tmux"] + args
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )

    def open_window(
        self,
        title: str,
        command: str,
        working_directory: Optional[Path] = None,
    ) -> WindowHandle:
        """Open a new tmux window running the command."""
        window_id = str(uuid.uuid4())[:8]
        current_session = self._get_current_tmux_session()

        if not current_session:
            raise RuntimeError("Not running inside a tmux session")

        cmd_args = [
            "new-window",
            "-t", current_session,
        ]

        if working_directory:
            cmd_args.extend(["-c", str(working_directory)])

        cmd_args.append(command)

        try:
            self._run_tmux(cmd_args)
            # Rename the window
            self._run_tmux(["rename-window", "-t", f"{current_session}:!", title])
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to create tmux window: {e.stderr or str(e)}"
            ) from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("tmux command timed out") from None

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
        """Link a worker's window into the board's tmux session.

        Uses tmux link-window to share the worker's window pane.
        No nesting — the board session and worker session both
        point to the same underlying window.
        """
        window_id = str(uuid.uuid4())[:8]
        current_session = self._get_current_tmux_session()

        if not current_session:
            raise RuntimeError("Not running inside a tmux session")

        if not self._validate_tmux_session(session_name):
            raise ValueError(
                f"tmux session '{session_name}' not found or invalid. "
                "Session may have died or been killed. "
                "Try restarting the worker session."
            )

        try:
            # Check if a window with this title is already linked into the board session.
            # link-window is not idempotent — calling it twice creates duplicate windows.
            result = self._run_tmux([
                "list-windows", "-t", current_session, "-F", "#{window_name}",
            ])
            existing_names = result.stdout.strip().split("\n") if result.stdout.strip() else []
            if title in existing_names:
                # Window already linked; find its index and return a handle.
                index_result = self._run_tmux([
                    "list-windows", "-t", current_session, "-F",
                    "#{window_index} #{window_name}",
                ])
                for line in index_result.stdout.strip().split("\n"):
                    parts = line.split(" ", 1)
                    if len(parts) == 2 and parts[1] == title:
                        return WindowHandle(
                            window_id=parts[0],
                            terminal_type=self.terminal_type,
                            title=title,
                            session_name=session_name,
                        )

            # Link worker's window 0 into the board session.
            # Use raw session_name (no shlex.quote — this is a subprocess list, not a shell).
            self._run_tmux([
                "link-window",
                "-s", f"{session_name}:0",
                "-t", current_session,
            ])

            # Find the newly linked window (it's the highest-numbered one)
            result = self._run_tmux([
                "list-windows", "-t", current_session, "-F", "#{window_index}"
            ])
            window_indices = result.stdout.strip().split("\n")
            new_index = window_indices[-1]

            # Rename it
            self._run_tmux([
                "rename-window",
                "-t", f"{current_session}:{new_index}",
                title,
            ])

            # Switch to the new window so the user sees it immediately
            self._run_tmux([
                "select-window",
                "-t", f"{current_session}:{new_index}",
            ])

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to link worker window: {e.stderr or str(e)}"
            ) from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("tmux command timed out") from None

        return WindowHandle(
            window_id=window_id,
            terminal_type=self.terminal_type,
            title=title,
            session_name=session_name,
        )

    def close_window(self, handle: WindowHandle) -> bool:
        """Unlink the worker's window from the board session.

        Uses unlink-window so the worker's session keeps the window alive.
        """
        current_session = self._get_current_tmux_session()
        if not current_session:
            return False

        try:
            self._run_tmux([
                "unlink-window",
                "-t", f"{current_session}:{handle.title}",
            ])
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False


# Register this provider
register_provider(TerminalType.TMUX_LINK, TmuxLinkProvider)

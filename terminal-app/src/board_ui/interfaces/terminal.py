"""
Terminal emulator provider interface.

Defines the contract for spawning windows across different terminal emulators.
Implementations handle per-emulator specifics (Kitty, iTerm2, Terminal.app, etc).

Key principle: Board users never see terminal jargon. They click "Chat with CEO"
and a window opens. Closing the window never kills the worker - just disconnects.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class TerminalType(Enum):
    """Supported terminal emulators."""
    TMUX_LINK = "tmux-link"  # link-window into current tmux session (no nesting)
    KITTY = "kitty"
    ITERM2 = "iterm2"
    MACOS_TERMINAL = "terminal"
    WINDOWS_TERMINAL = "wt"
    GNOME_TERMINAL = "gnome-terminal"
    ALACRITTY = "alacritty"
    GENERIC = "generic"  # Fallback using $TERM


@dataclass(frozen=True)
class WindowHandle:
    """Handle to an opened terminal window.

    Immutable reference to track opened windows. Used for closing
    or checking if window is still open.
    """
    window_id: str
    terminal_type: TerminalType
    title: str
    session_name: Optional[str] = None  # tmux session attached to


class TerminalProvider(ABC):
    """Abstract interface for terminal emulator providers.

    Each implementation handles the specifics of one terminal emulator.
    The board UI uses this interface to spawn windows without knowing
    which terminal is being used.

    Contract guarantees:
    - open_window() spawns a new window, never takes over current terminal
    - Closing window (by user) detaches from session, never kills it
    - Multiple windows can attach to same session (for observation)
    """

    @property
    @abstractmethod
    def terminal_type(self) -> TerminalType:
        """Return which terminal this provider handles."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this terminal emulator is installed and usable.

        Returns:
            True if the terminal can be used, False otherwise.
        """
        ...

    @abstractmethod
    def open_window(
        self,
        title: str,
        command: str,
        working_directory: Optional[Path] = None,
    ) -> WindowHandle:
        """Open a new terminal window running the specified command.

        This spawns a completely new window - never takes over the current
        terminal. The user can close this window at any time without
        affecting the underlying process (if it's a tmux attach).

        Args:
            title: Window title (shown in title bar, taskbar)
            command: Command to run in the new window
            working_directory: Directory to start in (optional)

        Returns:
            Handle to the opened window for tracking
        """
        ...

    @abstractmethod
    def attach_to_session(
        self,
        title: str,
        session_name: str,
    ) -> WindowHandle:
        """Open a window attached to an existing tmux session.

        This is the primary way board members interact with workers.
        The window attaches to the worker's tmux session. Closing the
        window detaches - it never kills the session.

        Args:
            title: Window title (e.g., "Chat with CEO")
            session_name: tmux session name to attach to

        Returns:
            Handle to the opened window
        """
        ...

    def close_window(self, handle: WindowHandle) -> bool:
        """Close a previously opened window.

        Note: This is optional - users can just close windows normally.
        Provided for programmatic cleanup if needed.

        Args:
            handle: Window handle from open_window or attach_to_session

        Returns:
            True if window was closed, False if already closed or failed
        """
        # Default implementation: no-op, let user close manually
        return False

    def is_window_open(self, handle: WindowHandle) -> bool:
        """Check if a window is still open.

        Args:
            handle: Window handle to check

        Returns:
            True if window is still open, False otherwise
        """
        # Default: assume open (no tracking)
        return True

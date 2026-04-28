"""
Terminal emulator implementations.

Each provider implements the TerminalProvider interface for a specific
terminal emulator. The registry auto-detects available terminals.
"""

from .registry import get_terminal_provider, get_available_terminals
from .tmux_link import TmuxLinkProvider
from .kitty import KittyTerminal
from .iterm import ITermTerminal
from .macos import MacOSTerminal
from .generic import GenericTerminal

__all__ = [
    "get_terminal_provider",
    "get_available_terminals",
    "TmuxLinkProvider",
    "KittyTerminal",
    "ITermTerminal",
    "MacOSTerminal",
    "GenericTerminal",
]

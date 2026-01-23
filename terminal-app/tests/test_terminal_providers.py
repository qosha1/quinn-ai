"""Tests for terminal providers."""

import pytest
from unittest.mock import patch, MagicMock

from board_ui.interfaces.terminal import TerminalType, WindowHandle
from board_ui.terminals.registry import (
    register_provider,
    get_available_terminals,
    get_terminal_provider,
)
from board_ui.terminals.kitty import KittyTerminal
from board_ui.terminals.generic import GenericTerminal


class TestTerminalRegistry:
    """Tests for the terminal provider registry."""

    def test_generic_always_available(self):
        """Generic terminal should always be available."""
        provider = GenericTerminal()
        assert provider.is_available() is True
        assert provider.terminal_type == TerminalType.GENERIC

    def test_get_terminal_provider_returns_something(self):
        """Should always return at least the generic provider."""
        provider = get_terminal_provider()
        assert provider is not None

    def test_get_available_terminals_includes_generic(self):
        """Available terminals should include generic."""
        available = get_available_terminals()
        assert TerminalType.GENERIC in available


class TestKittyProvider:
    """Tests for the Kitty terminal provider."""

    def test_terminal_type(self):
        """Should report correct terminal type."""
        provider = KittyTerminal()
        assert provider.terminal_type == TerminalType.KITTY

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_is_available_when_kitty_installed(self, mock_run, mock_which):
        """Should be available when kitty is installed and remote control works."""
        mock_which.return_value = "/usr/bin/kitty"
        mock_run.return_value = MagicMock(returncode=0)

        provider = KittyTerminal()
        assert provider.is_available() is True

    @patch("shutil.which")
    def test_is_not_available_when_kitty_not_installed(self, mock_which):
        """Should not be available when kitty is not installed."""
        mock_which.return_value = None

        provider = KittyTerminal()
        assert provider.is_available() is False


class TestWindowHandle:
    """Tests for WindowHandle dataclass."""

    def test_window_handle_immutable(self):
        """WindowHandle should be immutable (frozen dataclass)."""
        handle = WindowHandle(
            window_id="abc123",
            terminal_type=TerminalType.KITTY,
            title="Test Window",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            handle.window_id = "different"

    def test_window_handle_with_session(self):
        """WindowHandle can include session name for tmux."""
        handle = WindowHandle(
            window_id="abc123",
            terminal_type=TerminalType.KITTY,
            title="CEO Chat",
            session_name="org-acme-ceo",
        )

        assert handle.session_name == "org-acme-ceo"

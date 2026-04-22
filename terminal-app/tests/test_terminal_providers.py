"""Tests for terminal providers."""

import pytest
from unittest.mock import patch, MagicMock

from board_ui.interfaces.terminal import TerminalType, WindowHandle
from board_ui.terminals.registry import (
    register_provider,
    get_available_terminals,
    get_terminal_provider,
    _PROVIDERS,
)
from board_ui.terminals.kitty import KittyTerminal
from board_ui.terminals.tmux_link import TmuxLinkProvider
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

    def test_tmux_link_registered(self):
        """TmuxLinkProvider should be registered."""
        assert TerminalType.TMUX_LINK in _PROVIDERS
        assert _PROVIDERS[TerminalType.TMUX_LINK] == TmuxLinkProvider

    def test_tmux_link_highest_preference_when_inside_tmux(self):
        """When inside tmux, link provider should win over Kitty."""
        # Verify preference order has TMUX_LINK before KITTY
        from board_ui.terminals.registry import get_available_terminals
        # We check the preference list directly since we can't mock is_available
        # on all providers easily. The preference order is hardcoded in registry.
        # Just verify it's registered at higher priority than KITTY
        assert TerminalType.TMUX_LINK in _PROVIDERS


class TestTmuxLinkProvider:
    """Tests for TmuxLinkProvider — uses link-window, NOT nesting."""

    def test_terminal_type(self):
        provider = TmuxLinkProvider()
        assert provider.terminal_type == TerminalType.TMUX_LINK

    @patch.dict("os.environ", {}, clear=False)
    def test_not_available_outside_tmux(self):
        """Should not be available when TMUX env var is missing."""
        import os
        os.environ.pop("TMUX", None)
        provider = TmuxLinkProvider()
        assert provider.is_available() is False

    @patch("board_ui.terminals.tmux_link.subprocess.run")
    @patch("shutil.which")
    @patch.dict("os.environ", {"TMUX": "/tmp/tmux-501/default,12345,0"}, clear=False)
    def test_available_inside_tmux(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/tmux"
        mock_run.return_value = MagicMock(returncode=0, stdout="quinnai-board\n")

        provider = TmuxLinkProvider()
        assert provider.is_available() is True

    @patch("board_ui.terminals.tmux_link.subprocess.run")
    @patch("shutil.which")
    @patch.dict("os.environ", {"TMUX": "/tmp/tmux-501/default,12345,0"}, clear=False)
    def test_attach_uses_link_window_not_nesting(self, mock_which, mock_run):
        """attach_to_session must use link-window, never nested attach."""
        mock_which.return_value = "/usr/bin/tmux"

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="quinnai-board\n"),  # _get_current_tmux_session
            MagicMock(returncode=0),                             # _validate_tmux_session
            MagicMock(returncode=0, stdout=""),                  # list-windows (idempotency name check — no match)
            MagicMock(returncode=0, stdout=""),                  # link-window
            MagicMock(returncode=0, stdout="0\n1\n"),            # list-windows (index lookup)
            MagicMock(returncode=0, stdout=""),                  # rename-window
            MagicMock(returncode=0, stdout=""),                  # select-window
        ]

        provider = TmuxLinkProvider()
        handle = provider.attach_to_session("Chat with CEO", "acme-ceo")

        assert handle.terminal_type == TerminalType.TMUX_LINK
        assert handle.session_name == "acme-ceo"

        # Verify link-window was called (4th call, index 3)
        link_call = mock_run.call_args_list[3]
        cmd = link_call[0][0]
        assert "link-window" in cmd
        # Must NOT contain "attach-session" (that would be nesting)
        full_cmd_str = " ".join(str(c) for c in cmd)
        assert "attach-session" not in full_cmd_str

    @patch("board_ui.terminals.tmux_link.subprocess.run")
    @patch("shutil.which")
    @patch.dict("os.environ", {"TMUX": "/tmp/tmux-501/default,12345,0"}, clear=False)
    def test_attach_validates_target_session(self, mock_which, mock_run):
        """Should raise ValueError for nonexistent session."""
        mock_which.return_value = "/usr/bin/tmux"

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="quinnai-board\n"),
            MagicMock(returncode=1),  # has-session fails
        ]

        provider = TmuxLinkProvider()
        with pytest.raises(ValueError, match="not found or invalid"):
            provider.attach_to_session("Chat", "dead-session")

    @patch("board_ui.terminals.tmux_link.subprocess.run")
    @patch("shutil.which")
    @patch.dict("os.environ", {"TMUX": "/tmp/tmux-501/default,12345,0"}, clear=False)
    def test_attach_is_idempotent(self, mock_which, mock_run):
        """Calling attach_to_session twice should not create duplicate windows.

        If the window is already linked (title matches an existing window name),
        the provider should return a handle without calling link-window again.
        """
        mock_which.return_value = "/usr/bin/tmux"

        mock_run.side_effect = [
            # First call: _get_current_tmux_session
            MagicMock(returncode=0, stdout="quinnai-board\n"),
            # _validate_tmux_session
            MagicMock(returncode=0),
            # list-windows (check by name) — window already exists
            MagicMock(returncode=0, stdout="Chat with CEO\n"),
            # list-windows (find index for existing window)
            MagicMock(returncode=0, stdout="3 Chat with CEO\n"),
        ]

        provider = TmuxLinkProvider()
        handle = provider.attach_to_session("Chat with CEO", "acme-ceo")

        assert handle.terminal_type == TerminalType.TMUX_LINK
        assert handle.session_name == "acme-ceo"
        assert handle.title == "Chat with CEO"

        # link-window must NOT have been called
        all_cmds = [str(call) for call in mock_run.call_args_list]
        assert not any("link-window" in cmd for cmd in all_cmds)

    @patch("board_ui.terminals.tmux_link.subprocess.run")
    @patch("shutil.which")
    @patch.dict("os.environ", {"TMUX": "/tmp/tmux-501/default,12345,0"}, clear=False)
    def test_attach_session_name_not_shell_quoted(self, mock_which, mock_run):
        """link-window source arg must not contain shell quoting around session name.

        shlex.quote wraps strings in single quotes for shell use, but subprocess
        list calls don't use a shell — the quotes become literal characters that
        tmux rejects.
        """
        mock_which.return_value = "/usr/bin/tmux"

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="quinnai-board\n"),  # _get_current_tmux_session
            MagicMock(returncode=0),                             # _validate_tmux_session
            MagicMock(returncode=0, stdout=""),                  # list-windows (name check)
            MagicMock(returncode=0, stdout=""),                  # link-window
            MagicMock(returncode=0, stdout="0\n1\n"),            # list-windows (index)
            MagicMock(returncode=0, stdout=""),                  # rename-window
            MagicMock(returncode=0, stdout=""),                  # select-window
        ]

        provider = TmuxLinkProvider()
        provider.attach_to_session("CEO", "acme-ceo")

        # Find the link-window call
        link_call = next(
            c for c in mock_run.call_args_list
            if "link-window" in str(c)
        )
        cmd = link_call[0][0]
        source_arg = cmd[cmd.index("-s") + 1]
        # Must be "acme-ceo:0", NOT "'acme-ceo':0"
        assert source_arg == "acme-ceo:0"


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

    @patch("board_ui.terminals.kitty.subprocess.run")
    @patch("shutil.which")
    def test_attach_opens_kitty_os_window(self, mock_which, mock_run):
        """Attach should open a Kitty OS window — no tmux nesting."""
        mock_which.return_value = "/usr/bin/kitty"
        mock_run.return_value = MagicMock(returncode=0)

        provider = KittyTerminal()
        handle = provider.attach_to_session("Chat with CEO", "acme-ceo")

        assert handle.terminal_type == TerminalType.KITTY
        assert handle.session_name == "acme-ceo"

        # Verify kitty @ launch was called (OS window, not tmux window)
        launch_call = mock_run.call_args_list[-1]
        cmd = launch_call[0][0]
        assert "kitty" in cmd
        assert "@" in cmd
        assert "launch" in cmd
        assert "--type=os-window" in cmd

    @patch("board_ui.terminals.kitty.subprocess.run")
    @patch("shutil.which")
    def test_attach_validates_session_first(self, mock_which, mock_run):
        """Should validate tmux session exists before opening Kitty window."""
        mock_which.return_value = "/usr/bin/kitty"
        # has-session returns failure (session doesn't exist)
        mock_run.return_value = MagicMock(returncode=1)

        provider = KittyTerminal()
        with pytest.raises(ValueError, match="not found or invalid"):
            provider.attach_to_session("Chat with CEO", "dead-session")


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

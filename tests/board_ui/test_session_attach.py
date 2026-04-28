"""Tests for session attachment and window spawning.

Tests attaching to tmux sessions via terminal providers.
"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from board_ui.interfaces.terminal import WindowHandle, TerminalType
from board_ui.terminals.generic import GenericTerminal
from board_ui.terminals.kitty import KittyTerminal


class TestSessionAttach:
    """Tests for session attachment functionality."""

    def test_attach_to_tmux_session(self):
        """Should attach to an existing tmux session."""
        provider = GenericTerminal()

        # Mock tmux session existence check
        with patch("board_ui.terminals.generic.subprocess.run") as mock_run:
            # has-session succeeds
            mock_run.return_value = MagicMock(returncode=0)

            # Mock open_window to avoid actual terminal spawn
            with patch.object(provider, "open_window") as mock_open:
                mock_open.return_value = WindowHandle(
                    window_id="test-123",
                    terminal_type=TerminalType.GENERIC,
                    title="Test Session",
                    session_name="test-session",
                )

                # Attach to session
                handle = provider.attach_to_session(
                    title="Test Session",
                    session_name="test-session",
                )

                # Should return a window handle
                assert handle is not None
                assert handle.session_name == "test-session"
                assert handle.title == "Test Session"

    def test_attach_opens_new_window(self):
        """Attach should open a new terminal window."""
        provider = GenericTerminal()

        # Mock tmux validation to pass
        with patch.object(provider, "_validate_tmux_session", return_value=True):
            # Mock open_window to track call
            with patch.object(provider, "open_window") as mock_open:
                mock_open.return_value = WindowHandle(
                    window_id="win-456",
                    terminal_type=TerminalType.GENERIC,
                    title="Worker Chat",
                    session_name="worker-session",
                )

                handle = provider.attach_to_session(
                    title="Worker Chat",
                    session_name="worker-session",
                )

                # Should have called open_window with tmux attach command
                mock_open.assert_called_once()
                call_args = mock_open.call_args
                assert "Worker Chat" in call_args[0]
                assert "tmux attach-session" in call_args[0][1]
                assert "worker-session" in call_args[0][1]

    def test_close_window_detaches_only(self):
        """Closing window should detach, not kill session."""
        # This is a behavioral test - documented in provider contract
        provider = KittyTerminal()

        # The attach command uses "tmux attach-session" which detaches on window close
        # This is guaranteed by tmux behavior, not something we test here
        # The provider documentation guarantees this contract

        # Test that the command uses tmux attach (which detaches on close)
        with patch.object(provider, "_validate_tmux_session", return_value=True):
            with patch("board_ui.terminals.kitty.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                provider.attach_to_session(
                    title="Test",
                    session_name="test-session",
                )

                # Verify tmux attach command was used (guarantees detach behavior)
                call_args = mock_run.call_args
                cmd = call_args[0][0]
                assert "tmux attach-session" in " ".join(cmd)

    def test_worker_continues_after_detach(self):
        """Worker should continue running after window closed."""
        # This test validates the contract, not the implementation
        # tmux attach-session guarantees that the session continues
        # after detach - this is fundamental tmux behavior

        # We verify the provider uses the correct command
        provider = GenericTerminal()

        with patch.object(provider, "_validate_tmux_session", return_value=True):
            with patch("board_ui.terminals.generic.subprocess.Popen") as mock_popen:
                with patch("board_ui.terminals.generic.platform.system", return_value="Linux"):
                    provider.attach_to_session(
                        title="Test",
                        session_name="test-session",
                    )

                    # Verify tmux attach was used (session persists after detach)
                    call_args = mock_popen.call_args
                    cmd = call_args[0][0]
                    assert any("tmux attach-session" in str(c) for c in cmd)

    def test_multiple_attach_same_session(self):
        """Multiple windows can attach to same session."""
        provider = GenericTerminal()

        # Mock tmux validation
        with patch.object(provider, "_validate_tmux_session", return_value=True):
            with patch.object(provider, "open_window") as mock_open:
                mock_open.side_effect = [
                    WindowHandle("win-1", TerminalType.GENERIC, "Window 1", "shared-session"),
                    WindowHandle("win-2", TerminalType.GENERIC, "Window 2", "shared-session"),
                ]

                # Attach first window
                handle1 = provider.attach_to_session(
                    title="Window 1",
                    session_name="shared-session",
                )

                # Attach second window to same session
                handle2 = provider.attach_to_session(
                    title="Window 2",
                    session_name="shared-session",
                )

                # Both should succeed
                assert handle1.session_name == "shared-session"
                assert handle2.session_name == "shared-session"
                assert handle1.window_id != handle2.window_id

    def test_session_not_found_error(self):
        """Should handle missing session gracefully."""
        provider = GenericTerminal()

        # Mock tmux session check to fail
        with patch("board_ui.terminals.generic.subprocess.run") as mock_run:
            # has-session returns non-zero (session doesn't exist)
            mock_run.return_value = MagicMock(returncode=1)

            # Attach to non-existent session should raise ValueError
            with pytest.raises(ValueError) as exc_info:
                provider.attach_to_session(
                    title="Test",
                    session_name="nonexistent-session",
                )

            # Error should mention the session name
            assert "nonexistent-session" in str(exc_info.value)
            assert "not found" in str(exc_info.value)

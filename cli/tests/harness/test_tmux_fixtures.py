"""Tests for the tmux harness itself (Layer 2).

Skipped automatically when tmux is not on PATH; runs full integration
when available.
"""

import time

import pytest


@pytest.mark.tmux
def test_marker_runs_when_tmux_available(tmux_with_fake_cli):
    """If we got here, the @pytest.mark.tmux gate let us through."""
    assert tmux_with_fake_cli.session_name


@pytest.mark.tmux
def test_fake_cli_session_is_alive_immediately(tmux_with_fake_cli):
    """After the fixture yields, the tmux session must be alive."""
    assert tmux_with_fake_cli.is_alive() is True


@pytest.mark.tmux
def test_fake_cli_banner_visible_in_pane(tmux_with_fake_cli):
    """capture-pane must show the FAKE-CLI banner from fake_cli.py."""
    output = tmux_with_fake_cli.spawner.read_output(tmux_with_fake_cli.session_name)
    # The banner format is: 'FAKE-CLI: ready worker=fakecli-test pid=...'
    assert "FAKE-CLI: ready" in output, (
        f"Expected fake_cli banner in tmux pane. Got:\n{output}"
    )
    assert "worker=fakecli-test" in output


@pytest.mark.tmux
def test_send_input_appears_in_pane(tmux_with_fake_cli):
    """send_input via TmuxSpawner must reach fake_cli's stdin and echo back."""
    handle = tmux_with_fake_cli
    # send-keys followed by Enter (TmuxSpawner.send_input handles this)
    handle.spawner.send_input(handle.session_name, "ping-from-test\n")
    # Give fake_cli a moment to echo
    time.sleep(0.3)
    output = handle.spawner.read_output(handle.session_name)
    assert "ECHO: ping-from-test" in output, (
        f"fake_cli should echo stdin lines. Got:\n{output}"
    )


@pytest.mark.tmux
def test_kill_terminates_session(tmux_with_fake_cli):
    """Calling .kill() must stop the underlying tmux session."""
    handle = tmux_with_fake_cli
    assert handle.is_alive()
    handle.kill()
    # tmux can take a moment to reap
    time.sleep(0.2)
    assert handle.is_alive() is False

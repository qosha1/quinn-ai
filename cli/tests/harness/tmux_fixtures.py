"""Layer-2 harness: real tmux + fake_cli.

Fixtures here spawn an actual tmux session running cli/tests/harness/fake_cli.py.
Tests using these fixtures must be marked @pytest.mark.tmux so they
auto-skip when tmux isn't on PATH.

Pattern::

    @pytest.mark.tmux
    def test_logs_reads_real_scrollback(tmux_with_fake_cli):
        result = tmux_with_fake_cli
        # result.session_id is the tmux session name; the spawner pid is in result.pid
        # ... drive `qn org logs` against this session ...
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import pytest

from cli.core.sessions.spawner import SpawnerConfig, SpawnResult
from cli.core.sessions.tmux_spawner import TmuxSpawner

# Path to the fake CLI script (run via `python -m cli.tests.harness.fake_cli`)
FAKE_CLI_MODULE = "cli.tests.harness.fake_cli"


def tmux_available() -> bool:
    return shutil.which("tmux") is not None


@dataclass
class TmuxSession:
    """Handle to a live tmux session spawned by these fixtures."""

    session_name: str
    pid: Optional[int]
    spawner: TmuxSpawner

    def kill(self) -> None:
        """Kill the underlying tmux session (no-op if already gone)."""
        if self.session_name:
            self.spawner.stop(self.session_name, force=True)

    def is_alive(self) -> bool:
        return self.spawner.is_alive(self.session_name)


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """Auto-skip @pytest.mark.tmux tests when tmux isn't available.

    Imported by cli/tests/conftest.py so it runs on collection.
    """
    if tmux_available():
        return
    skip_tmux = pytest.mark.skip(reason="requires tmux on PATH (install: brew install tmux)")
    for item in items:
        if "tmux" in item.keywords:
            item.add_marker(skip_tmux)


@pytest.fixture
def tmux_with_fake_cli() -> Iterator[TmuxSession]:
    """Spawn a real tmux session running fake_cli.py via TmuxSpawner.

    Yields a TmuxSession handle. Cleans up the tmux session on teardown
    even if the test fails.
    """
    if not tmux_available():
        pytest.skip("tmux not on PATH")

    spawner = TmuxSpawner()
    # Run fake_cli as a python module so import resolution works.
    # env_vars now reach the process after the quinn-ai-ad8 fix.
    config = SpawnerConfig(
        command=sys.executable,
        args=["-m", FAKE_CLI_MODULE, "--interval", "0.2"],
        session_name=f"qn-fakecli-{int(time.time() * 1000) % 100000}",
        worker_id="fakecli-test",
        env_vars={"QUINN_WORKER_ID": "fakecli-test"},
    )
    result: SpawnResult = spawner.spawn(config)
    if not result.success:
        pytest.fail(f"failed to spawn fake_cli tmux session: {result.error}")

    handle = TmuxSession(
        session_name=result.session_id,
        pid=result.pid,
        spawner=spawner,
    )
    # Give fake_cli a moment to print its banner
    time.sleep(0.4)

    try:
        yield handle
    finally:
        handle.kill()

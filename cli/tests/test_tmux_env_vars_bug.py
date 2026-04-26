"""Regression test for quinn-ai-ad8.

TmuxSpawner.spawn() previously set env vars via 'tmux set-environment'
BEFORE running 'tmux new-session', so the values were lost. This test
verifies env vars passed in SpawnerConfig actually reach the spawned
process (using fake_cli, which prints worker= from the env var).
"""

import shutil
import sys
import time

import pytest

from cli.core.sessions.spawner import SpawnerConfig
from cli.core.sessions.tmux_spawner import TmuxSpawner


pytestmark = pytest.mark.tmux


@pytest.fixture
def spawner():
    if shutil.which("tmux") is None:
        pytest.skip("tmux not on PATH")
    return TmuxSpawner()


def test_env_vars_reach_spawned_process(spawner):
    """fake_cli reads QUINN_WORKER_ID from env if --worker isn't passed.
    A working spawner must propagate env_vars so the banner shows the
    expected worker id, not the literal 'unknown'."""
    session_name = f"qn-envtest-{int(time.time() * 1000) % 100000}"
    config = SpawnerConfig(
        command=sys.executable,
        # Note: NO --worker arg, so fake_cli MUST read env. Long interval
        # so the process stays alive while we capture the pane.
        args=["-m", "cli.tests.harness.fake_cli", "--interval", "5"],
        session_name=session_name,
        worker_id="env-test-worker",
        env_vars={"QUINN_WORKER_ID": "env-test-worker"},
    )
    try:
        result = spawner.spawn(config)
        assert result.success, f"spawn failed: {result.error}"
        time.sleep(0.4)
        output = spawner.read_output(session_name)
        assert "FAKE-CLI: ready" in output, f"banner missing:\n{output}"
        assert "worker=env-test-worker" in output, (
            f"env var did not reach process. Banner shows 'worker=unknown' "
            f"meaning QUINN_WORKER_ID was lost. Pane:\n{output}"
        )
    finally:
        spawner.stop(session_name, force=True)


def test_multiple_env_vars(spawner):
    """All env_vars must propagate, not just one."""
    import subprocess
    session_name = f"qn-envtest2-{int(time.time() * 1000) % 100000}"
    # Use 'env' as the command so we can inspect which vars are set
    config = SpawnerConfig(
        command="sh",
        args=["-c", "env > /tmp/qn-envtest-out.txt; sleep 1"],
        session_name=session_name,
        env_vars={"FOO": "bar", "BAZ": "qux", "QUINN_WORKER_ID": "multi"},
    )
    try:
        result = spawner.spawn(config)
        assert result.success, result.error
        time.sleep(0.5)
        out = subprocess.run(
            ["cat", "/tmp/qn-envtest-out.txt"], capture_output=True, text=True
        ).stdout
        assert "FOO=bar" in out, f"FOO missing:\n{out}"
        assert "BAZ=qux" in out, f"BAZ missing:\n{out}"
        assert "QUINN_WORKER_ID=multi" in out, f"QUINN_WORKER_ID missing:\n{out}"
    finally:
        spawner.stop(session_name, force=True)
        subprocess.run(["rm", "-f", "/tmp/qn-envtest-out.txt"])

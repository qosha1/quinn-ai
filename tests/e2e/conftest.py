"""
Pytest fixtures for E2E CLI tests.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import pytest


# ---------------------------------------------------------------------------
# bd-availability gate: e2e tests need a real bd binary
# ---------------------------------------------------------------------------

def _bd_available() -> bool:
    """True iff a usable bd binary is on PATH or in cli/bin/{platform}/bd."""
    if shutil.which("bd"):
        return True
    project_root = Path(__file__).parent.parent.parent
    # Best-effort platform detection matching cli.core.bd_wrapper
    import platform

    osname = "darwin" if sys.platform == "darwin" else "linux"
    arch = "arm64" if platform.machine() in ("arm64", "aarch64") else "amd64"
    bundled = project_root / "cli" / "bin" / f"{osname}-{arch}" / "bd"
    return bundled.exists() and os.access(bundled, os.X_OK)


# Apply skip-if-no-bd to every test in tests/e2e/ via conftest.
collect_ignore_glob = []
if not _bd_available():
    pytest.skip(
        "bd binary not found — install with 'brew install bd' or place under "
        "cli/bin/{platform}/bd. The e2e suite requires a real bd to exercise "
        "qn org init.",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Env hygiene: strip provider API keys + QUINN_* from every subprocess
# ---------------------------------------------------------------------------

_PROVIDER_KEY_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
)
_QUINN_AMBIENT_VARS = ("QUINN_ORG_PATH", "QUINN_WORKER_ID")


@pytest.fixture(autouse=True)
def env_hygiene(monkeypatch):
    """Strip provider keys + QUINN_* from os.environ for every e2e test.

    Prevents the dev shell's keys from leaking into mocked-provider tests
    and prevents QUINN_ORG_PATH from accidentally targeting the wrong org.
    monkeypatch restores everything on teardown.
    """
    for var in _PROVIDER_KEY_VARS + _QUINN_AMBIENT_VARS:
        monkeypatch.delenv(var, raising=False)
    # Strip CLAUDE_* prefix variants too (Claude CLI auth state)
    for key in [k for k in os.environ if k.startswith("CLAUDE_")]:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_org_dir(tmp_path):
    """Create a temporary directory for org testing.

    Yields:
        Path to temporary org directory.

    Note:
        Automatically cleaned up after test.
    """
    org_dir = tmp_path / "test-org"
    org_dir.mkdir()
    yield org_dir
    # Cleanup handled by tmp_path fixture


@pytest.fixture
def cli_runner():
    """Factory for running CLI commands.

    Returns:
        Callable that runs CLI commands and returns result.
    """
    def run_command(
        args: List[str],
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        check: bool = False,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess:
        """Run a CLI command via subprocess.

        Args:
            args: Command arguments (e.g., ["org", "init"])
            cwd: Working directory for the command (not for Python)
            env: Environment variables (merged with os.environ)
            check: Raise CalledProcessError on non-zero exit
            timeout: Command timeout in seconds

        Returns:
            CompletedProcess with returncode, stdout, stderr
        """
        # Build full command: <python> -m cli.commands.main <args>
        # Use sys.executable so the subprocess inherits the same interpreter
        # pytest is running under (works in venv + CI without relying on a
        # bare `python` binary being on PATH).
        cmd = [sys.executable, "-m", "cli.commands.main"] + args

        # Merge environment variables
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        # Set PYTHONPATH to ensure cli module is importable
        # Get the project root (where cli/ directory lives)
        project_root = Path(__file__).parent.parent.parent
        full_env["PYTHONPATH"] = str(project_root)

        # Run command from project root (so Python can import cli)
        # but use 'cwd' for where the actual command thinks it's running
        result = subprocess.run(
            cmd,
            cwd=cwd or project_root,
            env=full_env,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )

        return result

    return run_command


@pytest.fixture
def initialized_org(temp_org_dir, cli_runner):
    """Create an initialized org for testing.

    Runs `qn org init` and returns the org directory path.

    Yields:
        Path to initialized org directory.
    """
    # Run org init
    result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "init"],
        check=True,
    )

    assert result.returncode == 0
    assert "Initialized organization" in result.stdout

    yield temp_org_dir


@pytest.fixture
def running_org(initialized_org, cli_runner):
    """Create a running org for testing (without spawning CEO).

    Runs `qn org start --no-spawn-ceo` to avoid session spawning complexity.

    Yields:
        Path to running org directory.
    """
    # Start org without spawning CEO (to avoid session complexity)
    result = cli_runner(
        [
            "--org-path", str(initialized_org),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    assert result.returncode == 0

    yield initialized_org

    # Cleanup: stop org
    cli_runner(
        [
            "--org-path", str(initialized_org),
            "org", "stop",
            "--force",
            "--yes",
        ],
    )


@pytest.fixture
def qn_runner():
    """Like cli_runner but invokes the installed 'qn' entry-point script.

    Tests one more layer than 'python -m cli.commands.main' — the
    setuptools-generated qn shim. Use this in new e2e tests; existing
    smoke tests may keep cli_runner.

    Resolves 'qn' from (in order):
      1. PATH (`shutil.which`)
      2. The venv next to the python interpreter pytest is running under
         (`<sys.executable dir>/qn`) — handles the common case where the
         user runs `.venv/bin/pytest` without activating the venv.
      3. The project-root `.venv/bin/qn`.
    Skips the test if none of those resolve.
    """
    qn_bin = shutil.which("qn")
    if not qn_bin:
        # Try the venv that pytest is running under
        candidate = Path(sys.executable).parent / "qn"
        if candidate.exists() and os.access(candidate, os.X_OK):
            qn_bin = str(candidate)
    if not qn_bin:
        # Fall back to project-root .venv/bin/qn
        project_root = Path(__file__).parent.parent.parent
        candidate = project_root / ".venv" / "bin" / "qn"
        if candidate.exists() and os.access(candidate, os.X_OK):
            qn_bin = str(candidate)
    if not qn_bin:
        pytest.skip("qn binary not found (run 'pip install -e .' in your venv)")

    def run_command(
        args: List[str],
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        check: bool = False,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess:
        """Run 'qn ...args' as a subprocess. Returns the CompletedProcess."""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        return subprocess.run(
            [qn_bin] + list(args),
            cwd=str(cwd) if cwd else None,
            env=full_env,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )

    return run_command


@pytest.fixture
def org_with_ceo(running_org):
    """Alias for running_org — semantic name for the 'init + start --no-spawn-ceo' baseline.

    Use this fixture name in new e2e tests where the test cares about
    the running-org-with-CEO state (not just the side effect of having
    a running org). Kept as a thin alias to avoid renaming the existing
    smoke test fixture.
    """
    yield running_org


_HIRE_ID_PATTERN = re.compile(r"\b(wrkr-[0-9a-f]+)\b")


def _extract_worker_id(output: str) -> Optional[str]:
    """Pull the 'wrkr-XXXX' id out of `qn org hire` stdout.

    qn org hire prints a multi-line block including 'ID: wrkr-a1b2c3'.
    Returns the first match or None.
    """
    match = _HIRE_ID_PATTERN.search(output)
    return match.group(1) if match else None


@pytest.fixture
def hired_team(org_with_ceo, qn_runner, request):
    """Hire N workers under CEO for tests that need a populated team.

    Parametrize indirectly to control N:

        @pytest.mark.parametrize('hired_team', [3], indirect=True)
        def test_thing(hired_team):
            assert len(hired_team) == 3

    Default N=2 if no parametrization is provided. Returns a list of
    worker IDs in hire order.
    """
    n = getattr(request, "param", 2)
    worker_ids: List[str] = []
    for i in range(n):
        result = qn_runner(
            [
                "--org-path", str(org_with_ceo),
                "org", "hire",
                "--name", f"worker{i}",
                "--role", "Engineer",
                "--manager", "ceo",
            ],
            check=False,
        )
        if result.returncode != 0:
            pytest.fail(
                f"hired_team fixture: 'qn org hire' #{i} failed "
                f"(exit {result.returncode})\nstdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
        worker_id = _extract_worker_id(result.stdout)
        if not worker_id:
            pytest.fail(
                f"hired_team fixture: could not extract worker_id from "
                f"hire #{i} output:\n{result.stdout}"
            )
        worker_ids.append(worker_id)

    return worker_ids


@pytest.fixture
def mock_provider_config(temp_org_dir):
    """Create a mock provider config for testing.

    Creates config/providers.yaml with test settings.
    """
    config_dir = temp_org_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "providers.yaml"
    config_file.write_text("""
providers:
  claude_code:
    enabled: true
    model: claude-sonnet-4-5
    api_key_env: ANTHROPIC_API_KEY

  test_provider:
    enabled: false
    model: test-model
""")

    return config_file

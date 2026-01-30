"""
Pytest fixtures for E2E CLI tests.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import pytest


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
        # Build full command: python -m cli.commands.main <args>
        cmd = ["python", "-m", "cli.commands.main"] + args

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

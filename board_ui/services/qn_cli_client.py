"""Single adapter for invoking the `qn` CLI.

Replaces ~14 scattered `subprocess.run([..., "qn", ...])` call sites across
services, commanders, readers, and views. Owns command resolution
(venv → PATH → sys.executable -m fallback) and uniform timeout / error
handling. Returns a normalized `CommandResult` instead of mixing booleans,
tuples, and CompletedProcess objects everywhere.

The previous module-global `_qn_command_cache` is gone — the cache now lives
on the QnCliClient instance. A lazy default instance is exposed via
`get_default_qn_cli()` for callers that don't take a client by injection.
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..constants import (
    QN_DEFAULT_TIMEOUT_SECONDS,
    QN_HELP_TIMEOUT_SECONDS,
    QN_RESTART_TIMEOUT_SECONDS,
)


@dataclass
class CommandResult:
    """Normalized result of a `qn` invocation. Never raises."""

    success: bool
    returncode: int
    stdout: str
    stderr: str
    error_message: str  # empty when success; else best-available error string
    timed_out: bool = False

    @property
    def output(self) -> str:
        """stdout, falling back to stderr — useful for messages on success."""
        return self.stdout.strip() or self.stderr.strip()


def _resolve_qn_command() -> list[str]:
    """Find the qn CLI: same-venv binary, then PATH, then python -m fallback.

    Caller is expected to validate by running `--help`; this function only
    finds candidates.
    """
    venv_qn = Path(sys.executable).parent / "qn"
    if venv_qn.exists():
        return [str(venv_qn)]
    if shutil.which("qn"):
        return ["qn"]
    return [sys.executable, "-m", "cli.commands.main"]


class QnCliClient:
    """Adapter for the `qn` CLI. Holds the resolved command + runs subcommands."""

    def __init__(self, command: Optional[list[str]] = None) -> None:
        """Args:
        command: Override for tests. When None, resolves once via
            _resolve_qn_command() and caches on the instance.
        """
        self._command = list(command) if command else _resolve_qn_command()

    @property
    def command(self) -> list[str]:
        """Currently-resolved invocation prefix (e.g. ['/path/to/qn'])."""
        return list(self._command)

    def run(
        self,
        args: list[str],
        *,
        timeout: float = QN_DEFAULT_TIMEOUT_SECONDS,
        cwd: Optional[Path] = None,
    ) -> CommandResult:
        """Run `qn <args>` with a timeout. Always returns a CommandResult."""
        try:
            cp = subprocess.run(
                self._command + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd) if cwd else None,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr="",
                error_message=f"Command timed out after {timeout:.0f}s",
                timed_out=True,
            )
        except FileNotFoundError:
            return CommandResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr="",
                error_message=(
                    f"qn CLI not found at: {self._command[0]}\n"
                    "Install with: pip install -e .\n"
                    "Or ensure you're running from the quinnai virtual environment."
                ),
            )
        except Exception as e:
            return CommandResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr="",
                error_message=f"Error running qn: {e}",
            )

        if cp.returncode == 0:
            return CommandResult(
                success=True,
                returncode=0,
                stdout=cp.stdout,
                stderr=cp.stderr,
                error_message="",
            )

        error = cp.stderr.strip() or cp.stdout.strip() or f"exit {cp.returncode}"
        return CommandResult(
            success=False,
            returncode=cp.returncode,
            stdout=cp.stdout,
            stderr=cp.stderr,
            error_message=error,
        )

    def available(self) -> tuple[bool, str]:
        """Verify the resolved qn command actually responds (`qn --help`)."""
        result = self.run(["--help"], timeout=QN_HELP_TIMEOUT_SECONDS)
        return result.success, result.error_message

    # ---- convenience helpers for common operations ----

    def org_start(
        self,
        org_path: Path,
        *,
        spawn_ceo: bool = True,
        provider: str = "claude_code",
        skip_config_validation: bool = False,
        timeout: float = QN_DEFAULT_TIMEOUT_SECONDS,
    ) -> CommandResult:
        args = ["--org-path", str(org_path), "org", "start"]
        if not spawn_ceo:
            args.append("--no-spawn-ceo")
        else:
            args.extend(["--provider", provider])
        # claude_code provider uses local Claude CLI auth — skip API key check.
        if skip_config_validation or provider == "claude_code":
            args.append("--skip-config-validation")
        return self.run(args, timeout=timeout, cwd=org_path)

    def org_stop(
        self,
        org_path: Path,
        *,
        force: bool = False,
        cleanup: bool = True,
        timeout: float = QN_DEFAULT_TIMEOUT_SECONDS,
    ) -> CommandResult:
        args = ["--org-path", str(org_path), "org", "stop", "--yes"]
        if force:
            args.append("--force")
        if not cleanup:
            args.append("--no-cleanup")
        return self.run(args, timeout=timeout, cwd=org_path)

    def org_restart(
        self,
        org_path: Path,
        *,
        skip_config_validation: bool = True,
        timeout: float = QN_RESTART_TIMEOUT_SECONDS,
    ) -> CommandResult:
        args = ["--org-path", str(org_path), "org", "restart"]
        if skip_config_validation:
            args.append("--skip-config-validation")
        return self.run(args, timeout=timeout, cwd=org_path)

    def wrkr_restart(
        self,
        org_path: Path,
        worker_id: str,
        *,
        force: bool = True,
        timeout: float = QN_DEFAULT_TIMEOUT_SECONDS,
    ) -> CommandResult:
        args = ["--org-path", str(org_path), "wrkr", "restart", worker_id]
        if force:
            args.append("--force")
        return self.run(args, timeout=timeout, cwd=org_path)

    def org_fire(
        self,
        org_path: Path,
        worker_id: str,
        *,
        force: bool = True,
        timeout: float = 10,
    ) -> CommandResult:
        args = ["--org-path", str(org_path), "org", "fire", worker_id]
        if force:
            args.append("--force")
        return self.run(args, timeout=timeout)

    def org_provider_list(
        self,
        org_path: Path,
        *,
        timeout: float = 5,
    ) -> CommandResult:
        return self.run(
            ["--org-path", str(org_path), "org", "provider", "list"],
            timeout=timeout,
        )

    def org_provider_default(
        self,
        org_path: Path,
        provider_name: str,
        *,
        timeout: float = 5,
    ) -> CommandResult:
        return self.run(
            ["--org-path", str(org_path), "org", "provider", "default", provider_name],
            timeout=timeout,
        )


_default_client: Optional[QnCliClient] = None


def get_default_qn_cli() -> QnCliClient:
    """Lazy default client — first call resolves the qn command and caches it."""
    global _default_client
    if _default_client is None:
        _default_client = QnCliClient()
    return _default_client


def reset_default_qn_cli_for_tests() -> None:
    """Reset the default client between tests that monkey-patch resolution."""
    global _default_client
    _default_client = None

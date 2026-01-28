"""
Org discovery service for the Board Terminal App.

Discovers available orgs and manages their lifecycle via subprocess calls
to the existing CLI. The board is independent of org lifecycle - it can run
without any org, and starting/stopping orgs is done through the qn CLI.
"""

import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..logging_config import get_board_logger

logger = get_board_logger(__name__)

# Module-level cache for the qn command
_qn_command_cache: Optional[list[str]] = None


@dataclass
class OrgInfo:
    """Information about a discovered org."""

    path: Path
    name: str
    status: str
    is_running: bool
    has_db: bool
    ceo_worker_id: Optional[str] = None
    worker_count: int = 0
    active_session_count: int = 0


@dataclass
class OrgConfig:
    """Configuration for an org (from config directory)."""

    path: Path
    name: str
    has_providers: bool = False
    has_worker_templates: bool = False
    default_provider: Optional[str] = None


@dataclass
class StartResult:
    """Result of starting an org."""

    success: bool
    message: str
    returncode: int = 0


@dataclass
class StopResult:
    """Result of stopping an org."""

    success: bool
    message: str
    returncode: int = 0


def _get_qn_command() -> list[str]:
    """Get the qn CLI command.

    Uses sys.executable to ensure we use the same Python environment.
    Falls back to 'qn' if installed in PATH. Caches the result for performance.

    Returns:
        Command list to invoke qn CLI
    """
    global _qn_command_cache

    if _qn_command_cache is not None:
        return _qn_command_cache

    # First try: qn in the same venv as sys.executable
    # This is the most reliable approach when running from a venv
    venv_bin_dir = Path(sys.executable).parent
    venv_qn = venv_bin_dir / "qn"
    if venv_qn.exists():
        try:
            result = subprocess.run(
                [str(venv_qn), "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                _qn_command_cache = [str(venv_qn)]
                return _qn_command_cache
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

    # Second try: qn in PATH (globally installed)
    if shutil.which("qn"):
        try:
            result = subprocess.run(
                ["qn", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                _qn_command_cache = ["qn"]
                return _qn_command_cache
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

    # Third try: sys.executable -m cli.commands.main (if cli is installed as module)
    module_cmd = [sys.executable, "-m", "cli.commands.main"]
    try:
        result = subprocess.run(
            module_cmd + ["--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            _qn_command_cache = module_cmd
            return _qn_command_cache
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    # Default fallback: assume qn in venv (will likely fail but provides consistent behavior)
    _qn_command_cache = [str(venv_qn)]
    return _qn_command_cache


def check_cli_available() -> tuple[bool, str]:
    """Check if the qn CLI is available.

    Uses _get_qn_command() to find the CLI and verifies it's working.

    Returns:
        Tuple of (is_available, error_message).
        If available: (True, "")
        If not available: (False, "helpful error message")
    """
    qn_cmd = _get_qn_command()

    try:
        result = subprocess.run(
            qn_cmd + ["--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, ""
        else:
            return False, f"qn CLI returned error (exit {result.returncode}): {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "CLI check timed out. The CLI may be hanging."
    except FileNotFoundError:
        return False, (
            f"qn CLI not found at: {qn_cmd[0]}\n"
            "Install with: pip install -e .\n"
            "Or ensure you're running from the quinnai virtual environment."
        )
    except Exception as e:
        return False, f"Error checking CLI availability: {e}"


def _get_db_path(org_path: Path) -> Path:
    """Get the database path for an org folder.

    Args:
        org_path: Path to org folder

    Returns:
        Path to quinn.db
    """
    return org_path / "live" / "quinn.db"


def validate_org_path(org_path: Path) -> tuple[bool, str]:
    """Validate that org_path exists and looks like a valid org.

    A valid org has either:
    - live/quinn.db (initialized org)
    - config/ directory (can be initialized)

    Args:
        org_path: Path to validate

    Returns:
        Tuple of (is_valid, error_message).
        If valid: (True, "")
        If invalid: (False, "helpful error message")
    """
    # Check that path exists
    if not org_path.exists():
        return False, f"Org path does not exist: {org_path}"

    # Check that it's a directory
    if not org_path.is_dir():
        return False, f"Org path is not a directory: {org_path}"

    # Check for valid org indicators
    db_path = _get_db_path(org_path)
    config_path = org_path / "config"

    if not db_path.exists() and not config_path.exists():
        return False, (
            f"Not a valid org directory: {org_path}\n"
            "Expected either live/quinn.db or config/ directory."
        )

    return True, ""


def _read_org_status(db_path: Path) -> tuple[str, Optional[str], int, int]:
    """Read org status from quinn.db.

    Args:
        db_path: Path to quinn.db file

    Returns:
        Tuple of (status, ceo_worker_id, worker_count, active_session_count)
    """
    if not db_path.exists():
        return "uninitialized", None, 0, 0

    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row

        # Get org status
        cursor = conn.execute(
            "SELECT status, ceo_worker_id FROM org_state WHERE id = 'default'"
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            return "uninitialized", None, 0, 0

        status = row["status"]
        ceo_worker_id = row["ceo_worker_id"]

        # Count workers
        cursor = conn.execute("SELECT COUNT(*) as count FROM workers")
        worker_count = cursor.fetchone()["count"]

        # Count active sessions
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM sessions WHERE state IN ('starting', 'idle', 'running')"
        )
        active_session_count = cursor.fetchone()["count"]

        conn.close()
        return status, ceo_worker_id, worker_count, active_session_count

    except sqlite3.Error:
        return "error", None, 0, 0


def discover_running_orgs(search_paths: list[Path]) -> list[OrgInfo]:
    """Find all orgs currently running.

    Checks for quinn.db with status='running' in each search path.

    Args:
        search_paths: List of paths to search for orgs

    Returns:
        List of OrgInfo for running orgs
    """
    running_orgs: list[OrgInfo] = []

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Check if search_path itself is an org
        db_path = _get_db_path(search_path)
        if db_path.exists():
            status, ceo_id, worker_count, session_count = _read_org_status(db_path)
            if status == "running":
                running_orgs.append(
                    OrgInfo(
                        path=search_path,
                        name=search_path.name,
                        status=status,
                        is_running=True,
                        has_db=True,
                        ceo_worker_id=ceo_id,
                        worker_count=worker_count,
                        active_session_count=session_count,
                    )
                )
            continue

        # Search subdirectories
        if search_path.is_dir():
            for child in search_path.iterdir():
                if not child.is_dir():
                    continue

                db_path = _get_db_path(child)
                if db_path.exists():
                    status, ceo_id, worker_count, session_count = _read_org_status(
                        db_path
                    )
                    if status == "running":
                        running_orgs.append(
                            OrgInfo(
                                path=child,
                                name=child.name,
                                status=status,
                                is_running=True,
                                has_db=True,
                                ceo_worker_id=ceo_id,
                                worker_count=worker_count,
                                active_session_count=session_count,
                            )
                        )

    return running_orgs


def discover_available_orgs(search_paths: list[Path]) -> list[OrgInfo]:
    """Find org folders that can be started.

    Looks for folders with a live/quinn.db or config/ directory.

    Args:
        search_paths: List of paths to search for orgs

    Returns:
        List of OrgInfo for all discoverable orgs (running and stopped)
    """
    logger.debug(f"Starting org discovery with search paths: {search_paths}")
    orgs: list[OrgInfo] = []
    seen_paths: set[Path] = set()

    for search_path in search_paths:
        try:
            if not search_path.exists():
                logger.debug(f"Search path does not exist: {search_path}")
                continue

            # Check if search_path itself is an org
            if _is_org_folder(search_path):
                if search_path not in seen_paths:
                    seen_paths.add(search_path)
                    orgs.append(_build_org_info(search_path))
                continue

            # Search subdirectories
            if search_path.is_dir():
                for child in search_path.iterdir():
                    try:
                        if not child.is_dir():
                            continue

                        if _is_org_folder(child) and child not in seen_paths:
                            seen_paths.add(child)
                            orgs.append(_build_org_info(child))
                    except (PermissionError, OSError) as e:
                        logger.warning(f"Permission denied accessing {child}: {e}")
                        continue
        except (PermissionError, OSError) as e:
            logger.warning(f"Permission denied accessing {search_path}: {e}")
            continue

    logger.info(f"Discovery complete: found {len(orgs)} org(s)")
    return orgs


def _is_org_folder(path: Path) -> bool:
    """Check if a path is an org folder.

    An org folder has either:
    - live/quinn.db (initialized org)
    - config/ directory (can be initialized)

    Args:
        path: Path to check

    Returns:
        True if path is an org folder
    """
    try:
        if not path.is_dir():
            return False

        db_path = _get_db_path(path)
        config_path = path / "config"

        return db_path.exists() or config_path.exists()
    except (PermissionError, OSError) as e:
        logger.warning(f"Permission denied checking {path}: {e}")
        return False


def _build_org_info(org_path: Path) -> OrgInfo:
    """Build OrgInfo for a discovered org folder.

    Args:
        org_path: Path to org folder

    Returns:
        OrgInfo with current status
    """
    db_path = _get_db_path(org_path)
    has_db = db_path.exists()

    if has_db:
        status, ceo_id, worker_count, session_count = _read_org_status(db_path)
    else:
        status = "uninitialized"
        ceo_id = None
        worker_count = 0
        session_count = 0

    return OrgInfo(
        path=org_path,
        name=org_path.name,
        status=status,
        is_running=(status == "running"),
        has_db=has_db,
        ceo_worker_id=ceo_id,
        worker_count=worker_count,
        active_session_count=session_count,
    )


def get_org_configs(search_paths: list[Path]) -> list[OrgConfig]:
    """List available org configurations.

    Returns information about config directories found in search paths.

    Args:
        search_paths: List of paths to search for org configs

    Returns:
        List of OrgConfig for discovered configs
    """
    configs: list[OrgConfig] = []
    seen_paths: set[Path] = set()

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Check if search_path itself has config
        config_dir = search_path / "config"
        if config_dir.exists() and config_dir.is_dir():
            if search_path not in seen_paths:
                seen_paths.add(search_path)
                configs.append(_build_org_config(search_path))
            continue

        # Search subdirectories
        if search_path.is_dir():
            for child in search_path.iterdir():
                if not child.is_dir():
                    continue

                config_dir = child / "config"
                if config_dir.exists() and config_dir.is_dir():
                    if child not in seen_paths:
                        seen_paths.add(child)
                        configs.append(_build_org_config(child))

    return configs


def _build_org_config(org_path: Path) -> OrgConfig:
    """Build OrgConfig for a discovered org folder.

    Args:
        org_path: Path to org folder

    Returns:
        OrgConfig with config information
    """
    config_dir = org_path / "config"
    providers_path = config_dir / "providers.yaml"
    templates_path = config_dir / "worker-templates.yaml"

    has_providers = providers_path.exists()
    has_templates = templates_path.exists()

    # Try to read default provider from providers.yaml
    default_provider = None
    if has_providers:
        try:
            import yaml

            with open(providers_path) as f:
                data = yaml.safe_load(f)
                if data:
                    default_provider = data.get("default")
        except Exception:
            pass

    return OrgConfig(
        path=org_path,
        name=org_path.name,
        has_providers=has_providers,
        has_worker_templates=has_templates,
        default_provider=default_provider,
    )


def start_org(
    org_path: Path,
    spawn_ceo: bool = True,
    provider: str = "claude_code",
    skip_config_validation: bool = False,
) -> StartResult:
    """Start an org using `qn org start` subprocess.

    Args:
        org_path: Path to org folder
        spawn_ceo: Whether to spawn CEO session (default True)
        provider: Session provider for CEO (default: claude_code)
        skip_config_validation: Skip provider validation (for testing)

    Returns:
        StartResult with success status and message
    """
    # Validate org path first
    is_valid, validation_error = validate_org_path(org_path)
    if not is_valid:
        return StartResult(
            success=False,
            message=validation_error,
            returncode=-1,
        )

    # Check CLI availability
    cli_available, cli_error = check_cli_available()
    if not cli_available:
        return StartResult(
            success=False,
            message=cli_error,
            returncode=-1,
        )

    cmd = _get_qn_command() + ["--org-path", str(org_path), "org", "start"]

    if not spawn_ceo:
        cmd.append("--no-spawn-ceo")
    else:
        cmd.extend(["--provider", provider])

    # claude_code provider uses local Claude CLI auth, doesn't need API keys
    # from providers.yaml - skip validation to avoid false "API key required" errors
    if skip_config_validation or provider == "claude_code":
        cmd.append("--skip-config-validation")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(org_path),
        )

        if result.returncode == 0:
            return StartResult(
                success=True,
                message=result.stdout.strip() or "Organization started successfully",
                returncode=0,
            )
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            return StartResult(
                success=False,
                message=error_msg or "Failed to start organization",
                returncode=result.returncode,
            )

    except subprocess.TimeoutExpired:
        return StartResult(
            success=False,
            message="Start command timed out after 30 seconds",
            returncode=-1,
        )
    except FileNotFoundError:
        return StartResult(
            success=False,
            message="qn CLI not found. Ensure quinnai-cli is installed.",
            returncode=-1,
        )
    except Exception as e:
        return StartResult(
            success=False,
            message=f"Error starting org: {e}",
            returncode=-1,
        )


def stop_org(
    org_path: Path,
    force: bool = False,
    cleanup: bool = True,
) -> StopResult:
    """Stop an org using `qn org stop` subprocess.

    Args:
        org_path: Path to org folder
        force: Force kill sessions without waiting
        cleanup: Run notification cleanup on stop

    Returns:
        StopResult with success status and message
    """
    # Validate org path first
    is_valid, validation_error = validate_org_path(org_path)
    if not is_valid:
        return StopResult(
            success=False,
            message=validation_error,
            returncode=-1,
        )

    # Check CLI availability
    cli_available, cli_error = check_cli_available()
    if not cli_available:
        return StopResult(
            success=False,
            message=cli_error,
            returncode=-1,
        )

    cmd = _get_qn_command() + ["--org-path", str(org_path), "org", "stop"]

    if force:
        cmd.append("--force")

    if not cleanup:
        cmd.append("--no-cleanup")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(org_path),
        )

        if result.returncode == 0:
            return StopResult(
                success=True,
                message=result.stdout.strip() or "Organization stopped successfully",
                returncode=0,
            )
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            return StopResult(
                success=False,
                message=error_msg or "Failed to stop organization",
                returncode=result.returncode,
            )

    except subprocess.TimeoutExpired:
        return StopResult(
            success=False,
            message="Stop command timed out after 30 seconds",
            returncode=-1,
        )
    except FileNotFoundError:
        return StopResult(
            success=False,
            message="qn CLI not found. Ensure quinnai-cli is installed.",
            returncode=-1,
        )
    except Exception as e:
        return StopResult(
            success=False,
            message=f"Error stopping org: {e}",
            returncode=-1,
        )


def restart_org(
    org_path: Path,
    spawn_ceo: bool = True,
    provider: str = "claude_code",
    skip_config_validation: bool = False,
    graceful_timeout: int = 10,
) -> StartResult:
    """Restart an org by stopping then starting it.

    Args:
        org_path: Path to org folder
        spawn_ceo: Whether to spawn CEO session on restart (default True)
        provider: Session provider for CEO (default: claude_code)
        skip_config_validation: Skip provider validation
        graceful_timeout: Seconds to wait for graceful shutdown

    Returns:
        StartResult with success status and message
    """
    # First, stop the org
    stop_result = stop_org(
        org_path=org_path,
        force=False,  # Try graceful first
        cleanup=True,
    )

    if not stop_result.success:
        # Stop failed - return the error
        return StartResult(
            success=False,
            message=f"Failed to stop org during restart: {stop_result.message}",
            returncode=stop_result.returncode,
        )

    # Stop succeeded, now start it
    start_result = start_org(
        org_path=org_path,
        spawn_ceo=spawn_ceo,
        provider=provider,
        skip_config_validation=skip_config_validation,
    )

    if start_result.success:
        return StartResult(
            success=True,
            message="Organization restarted successfully",
            returncode=0,
        )
    else:
        return StartResult(
            success=False,
            message=f"Org stopped but failed to restart: {start_result.message}",
            returncode=start_result.returncode,
        )


def get_org_status(org_path: Path) -> OrgInfo:
    """Get current status of a specific org.

    Args:
        org_path: Path to org folder

    Returns:
        OrgInfo with current status
    """
    return _build_org_info(org_path)


def refresh_org_info(org_info: OrgInfo) -> OrgInfo:
    """Refresh OrgInfo by re-reading from database.

    Args:
        org_info: Existing OrgInfo to refresh

    Returns:
        Updated OrgInfo with fresh data
    """
    return _build_org_info(org_info.path)

"""
Org discovery service for the Board Terminal App.

Discovers available orgs and manages their lifecycle via subprocess calls
to the existing CLI. The board is independent of org lifecycle - it can run
without any org, and starting/stopping orgs is done through the qn CLI.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..logging_config import get_board_logger
from .qn_cli_client import get_default_qn_cli

logger = get_board_logger(__name__)


@dataclass
class DiscoveredOrg:
    """An org found on disk by discovery (status as raw string from quinn.db).

    Distinct from interfaces.org_connection.OrgInfo, which is the canonical
    type used by views and the connection facade (status as OrgStatus enum,
    plus started_at/stopped_at). This shape is what discovery walks the
    filesystem to produce; the connection facade then re-reads richer state.
    """

    path: Path
    name: str
    status: str
    is_running: bool
    has_db: bool
    ceo_worker_id: Optional[str] = None
    worker_count: int = 0
    active_session_count: int = 0


@dataclass
class DiscoveredOrgConfig:
    """Config files an org has on disk, surfaced by discovery.

    Distinct from views.org_wizard.OrgConfig (new-org wizard form data).
    """

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


def check_cli_available() -> tuple[bool, str]:
    """Check if the qn CLI is available. Thin wrapper over QnCliClient."""
    return get_default_qn_cli().available()


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


def discover_running_orgs(search_paths: list[Path]) -> list[DiscoveredOrg]:
    """Find all orgs currently running.

    Checks for quinn.db with status='running' in each search path.

    Args:
        search_paths: List of paths to search for orgs

    Returns:
        List of DiscoveredOrg for running orgs
    """
    running_orgs: list[DiscoveredOrg] = []

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Check if search_path itself is an org
        db_path = _get_db_path(search_path)
        if db_path.exists():
            status, ceo_id, worker_count, session_count = _read_org_status(db_path)
            if status == "running":
                running_orgs.append(
                    DiscoveredOrg(
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
                            DiscoveredOrg(
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


def discover_available_orgs(search_paths: list[Path]) -> list[DiscoveredOrg]:
    """Find org folders that can be started.

    Looks for folders with a live/quinn.db or config/ directory.

    Args:
        search_paths: List of paths to search for orgs

    Returns:
        List of DiscoveredOrg for all discoverable orgs (running and stopped)
    """
    logger.debug(f"Starting org discovery with search paths: {search_paths}")
    orgs: list[DiscoveredOrg] = []
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


def _build_org_info(org_path: Path) -> DiscoveredOrg:
    """Build DiscoveredOrg for a discovered org folder.

    Args:
        org_path: Path to org folder

    Returns:
        DiscoveredOrg with current status
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

    return DiscoveredOrg(
        path=org_path,
        name=org_path.name,
        status=status,
        is_running=(status == "running"),
        has_db=has_db,
        ceo_worker_id=ceo_id,
        worker_count=worker_count,
        active_session_count=session_count,
    )


def get_org_configs(search_paths: list[Path]) -> list[DiscoveredOrgConfig]:
    """List available org configurations.

    Returns information about config directories found in search paths.

    Args:
        search_paths: List of paths to search for org configs

    Returns:
        List of DiscoveredOrgConfig for discovered configs
    """
    configs: list[DiscoveredOrgConfig] = []
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


def _build_org_config(org_path: Path) -> DiscoveredOrgConfig:
    """Build DiscoveredOrgConfig for a discovered org folder.

    Args:
        org_path: Path to org folder

    Returns:
        DiscoveredOrgConfig with config information
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

    return DiscoveredOrgConfig(
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
        return StartResult(success=False, message=cli_error, returncode=-1)

    result = get_default_qn_cli().org_start(
        org_path,
        spawn_ceo=spawn_ceo,
        provider=provider,
        skip_config_validation=skip_config_validation,
    )
    if result.success:
        return StartResult(
            success=True,
            message=result.output or "Organization started successfully",
            returncode=0,
        )
    return StartResult(
        success=False,
        message=result.error_message or "Failed to start organization",
        returncode=result.returncode,
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
        return StopResult(success=False, message=cli_error, returncode=-1)

    result = get_default_qn_cli().org_stop(org_path, force=force, cleanup=cleanup)
    if result.success:
        return StopResult(
            success=True,
            message=result.output or "Organization stopped successfully",
            returncode=0,
        )
    return StopResult(
        success=False,
        message=result.error_message or "Failed to stop organization",
        returncode=result.returncode,
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


def get_org_status(org_path: Path) -> DiscoveredOrg:
    """Get current status of a specific org.

    Args:
        org_path: Path to org folder

    Returns:
        DiscoveredOrg with current status
    """
    return _build_org_info(org_path)


def refresh_org_info(org_info: DiscoveredOrg) -> DiscoveredOrg:
    """Refresh DiscoveredOrg by re-reading from database.

    Args:
        org_info: Existing DiscoveredOrg to refresh

    Returns:
        Updated DiscoveredOrg with fresh data
    """
    return _build_org_info(org_info.path)

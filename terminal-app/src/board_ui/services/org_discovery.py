"""
Discover orgs on disk and surface their status.

Pure discovery: walks search paths, identifies org folders (a folder with
either live/quinn.db or config/), and builds DiscoveredOrg records by
peeking at quinn.db via org_status_reader.

Subprocess-driven org lifecycle (start/stop/restart) lives in org_subprocess.
Config-only discovery (folders with config/ but no db yet) lives in
org_config_discovery. Dataclasses live in discovery_types.

This module re-exports the symbols those neighbors define so existing
callers (services/__init__.py, tests, commanders) keep working without
import-path churn.
"""

from pathlib import Path

from ..logging_config import get_board_logger
from .discovery_types import (
    DiscoveredOrg,
    DiscoveredOrgConfig,
    StartResult,
    StopResult,
)
from .org_config_discovery import _build_org_config, get_org_configs
from .org_status_reader import read_org_status as _read_org_status
from .org_subprocess import (
    check_cli_available,
    restart_org,
    start_org,
    stop_org,
)

logger = get_board_logger(__name__)


def _get_db_path(org_path: Path) -> Path:
    return org_path / "live" / "quinn.db"


def validate_org_path(org_path: Path) -> tuple[bool, str]:
    """Validate that org_path looks like an org folder.

    A valid org folder has either live/quinn.db (initialized) or config/
    (can be initialized).
    """
    if not org_path.exists():
        return False, f"Org path does not exist: {org_path}"

    if not org_path.is_dir():
        return False, f"Org path is not a directory: {org_path}"

    db_path = _get_db_path(org_path)
    config_path = org_path / "config"

    if not db_path.exists() and not config_path.exists():
        return False, (
            f"Not a valid org directory: {org_path}\n"
            "Expected either live/quinn.db or config/ directory."
        )

    return True, ""


def discover_running_orgs(search_paths: list[Path]) -> list[DiscoveredOrg]:
    """Find all orgs currently running across search_paths.

    Only returns orgs whose quinn.db reports status='running'.
    """
    running: list[DiscoveredOrg] = []

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Search path itself might be an org
        db_path = _get_db_path(search_path)
        if db_path.exists():
            status, ceo_id, worker_count, session_count = _read_org_status(db_path)
            if status == "running":
                running.append(
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

        # Otherwise scan immediate subdirs
        if search_path.is_dir():
            for child in search_path.iterdir():
                if not child.is_dir():
                    continue
                db_path = _get_db_path(child)
                if db_path.exists():
                    status, ceo_id, worker_count, session_count = _read_org_status(db_path)
                    if status == "running":
                        running.append(
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

    return running


def discover_available_orgs(search_paths: list[Path]) -> list[DiscoveredOrg]:
    """Find all org folders under search_paths regardless of status."""
    logger.debug(f"Starting org discovery with search paths: {search_paths}")
    orgs: list[DiscoveredOrg] = []
    seen_paths: set[Path] = set()

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Search path itself might be an org
        if _is_org_folder(search_path):
            if search_path not in seen_paths:
                seen_paths.add(search_path)
                orgs.append(_build_org_info(search_path))
            continue

        if not search_path.is_dir():
            continue

        try:
            children = list(search_path.iterdir())
        except (PermissionError, OSError) as e:
            logger.warning(f"Permission denied accessing {search_path}: {e}")
            continue

        for child in children:
            try:
                if _is_org_folder(child) and child not in seen_paths:
                    seen_paths.add(child)
                    orgs.append(_build_org_info(child))
            except (PermissionError, OSError) as e:
                logger.warning(f"Permission denied accessing {child}: {e}")
                continue

    logger.info(f"Discovery complete: found {len(orgs)} org(s)")
    return orgs


def _is_org_folder(path: Path) -> bool:
    """Has either live/quinn.db (initialized) or config/ (can be initialized)."""
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
    """Build a DiscoveredOrg by peeking at the org's quinn.db."""
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


def get_org_status(org_path: Path) -> DiscoveredOrg:
    """Get the current status of a specific org folder."""
    return _build_org_info(org_path)


def refresh_org_info(org_info: DiscoveredOrg) -> DiscoveredOrg:
    """Re-read an org's status from disk."""
    return _build_org_info(org_info.path)


__all__ = [
    # Re-exports
    "DiscoveredOrg",
    "DiscoveredOrgConfig",
    "StartResult",
    "StopResult",
    "check_cli_available",
    "get_org_configs",
    "start_org",
    "stop_org",
    "restart_org",
    # Defined here
    "validate_org_path",
    "discover_running_orgs",
    "discover_available_orgs",
    "get_org_status",
    "refresh_org_info",
]

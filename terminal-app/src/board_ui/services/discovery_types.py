"""Dataclasses returned by discovery + lifecycle subprocess helpers.

Kept in their own module so org_discovery.py and org_subprocess.py can both
import them without circular dependency, and so consumers can grab the
types without pulling in the discovery code.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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
    """Result of starting an org via the qn CLI."""

    success: bool
    message: str
    returncode: int = 0


@dataclass
class StopResult:
    """Result of stopping an org via the qn CLI."""

    success: bool
    message: str
    returncode: int = 0

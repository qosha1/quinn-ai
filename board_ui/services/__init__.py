"""
Services for connecting to and interacting with orgs.
"""

# Org discovery (finding and listing orgs)
from .org_discovery import (
    DiscoveredOrg,
    DiscoveredOrgConfig,
    StartResult,
    StopResult,
    discover_running_orgs,
    discover_available_orgs,
    get_org_configs,
    start_org,
    stop_org,
    get_org_status,
    refresh_org_info,
)

# Org connection (connecting to and querying org data)
from .org_connection import (
    QuinnAIOrgConnection,
    OrgConnectionError,
    OrgNotFound,
    DatabaseNotFound,
)

__all__ = [
    # Org discovery
    "DiscoveredOrg",
    "DiscoveredOrgConfig",
    "StartResult",
    "StopResult",
    "discover_running_orgs",
    "discover_available_orgs",
    "get_org_configs",
    "start_org",
    "stop_org",
    "get_org_status",
    "refresh_org_info",
    # Org connection
    "QuinnAIOrgConnection",
    "OrgConnectionError",
    "OrgNotFound",
    "DatabaseNotFound",
]

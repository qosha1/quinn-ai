"""
Board UI views.

Each view is a Textual widget that renders a tab in the board UI.
"""

from .dashboard import DashboardView
from .okrs import OKRsView
from .team import TeamView
from .messages import MessagesView
from .no_org import NoOrgView, ConnectToOrg, StartOrg, ShowNewOrgWizard, RefreshOrgList
from .org_wizard import OrgInitWizard, OrgConfig

__all__ = [
    "DashboardView",
    "OKRsView",
    "TeamView",
    "MessagesView",
    "NoOrgView",
    "ConnectToOrg",
    "StartOrg",
    "ShowNewOrgWizard",
    "RefreshOrgList",
    "OrgInitWizard",
    "OrgConfig",
]

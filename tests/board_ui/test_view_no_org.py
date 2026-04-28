"""Tests for No Org view.

Tests the landing state when no org is connected.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from board_ui.views.no_org import (
    NoOrgView,
    OrgListItem,
    ConnectToOrg,
    StartOrg,
    ShowNewOrgWizard,
    RefreshOrgList,
)


class TestNoOrgView:
    """Tests for NoOrgView widget."""

    def test_no_org_view_with_empty_list(self):
        """Should show 'no orgs found' message when list is empty."""
        view = NoOrgView(available_orgs=[])
        assert view.available_orgs == []

    def test_no_org_view_with_orgs(self):
        """Should show list of available orgs."""
        orgs = [
            (Path("/tmp/org1"), "running"),
            (Path("/tmp/org2"), "stopped"),
        ]
        view = NoOrgView(available_orgs=orgs)
        assert len(view.available_orgs) == 2

    def test_org_list_item_creation(self):
        """OrgListItem should store path and status."""
        item = OrgListItem(Path("/tmp/test-org"), "running")
        assert item.org_path == Path("/tmp/test-org")
        assert item.org_status == "running"


class TestNoOrgMessages:
    """Tests for custom messages."""

    def test_connect_to_org_message(self):
        """ConnectToOrg should carry org path."""
        msg = ConnectToOrg(Path("/tmp/my-org"))
        assert msg.org_path == Path("/tmp/my-org")

    def test_start_org_message(self):
        """StartOrg should carry org path."""
        msg = StartOrg(Path("/tmp/my-org"))
        assert msg.org_path == Path("/tmp/my-org")

    def test_show_new_org_wizard_message(self):
        """ShowNewOrgWizard should be instantiable."""
        msg = ShowNewOrgWizard()
        assert msg is not None

    def test_refresh_org_list_message(self):
        """RefreshOrgList should be instantiable."""
        msg = RefreshOrgList()
        assert msg is not None

"""Helper for views that need the active org connection.

Replaces the boilerplate that appeared in 11+ places:

    if not hasattr(self.app, 'org_connection') or self.app.org_connection is None:
        ...handle no-org case...
        return
    conn = self.app.org_connection

with:

    conn = get_org_connection(self.app)
    if conn is None:
        ...handle no-org case...
        return

The defensive ``hasattr`` guard exists because some unit tests build views
against a stub app that doesn't expose ``org_connection`` at all.
``getattr(app, "org_connection", None)`` collapses both cases — missing
attribute and None value — into a single None.
"""

from typing import Any, Optional

from ..interfaces.org_connection import OrgConnection


def get_org_connection(app: Any) -> Optional[OrgConnection]:
    """Return the active org connection or None if disconnected."""
    return getattr(app, "org_connection", None)

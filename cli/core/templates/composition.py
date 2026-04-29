"""Parent-reference validator for org templates.

Per quinn-ai-iabn §C.2 + quinn-ai-u0h2 §1: composition is reference-existing only.
NO topological sort. NO cycle detection. The validator does single-edge checks:
given a template and a parent_team_name, verify the parent team exists, is active,
and has the right template_type.
"""

from __future__ import annotations

from typing import Any, Optional

from cli.core.templates.types import Template
from shared.exceptions import (
    TemplateMissingParent,
    TemplateParentTerminated,
    TemplateWrongParentType,
)


def _lookup_team(db: Any, parent_team_name: str) -> Optional[dict[str, Any]]:
    """Resolve a team by name. Tolerates two db shapes (per test fixture in 61hp).

    Phase 4 may consolidate on `get_team_by_name` once we extract programmatic
    helpers; for now we accept either a typed accessor or a generic fetchone.
    """
    if hasattr(db, "get_team_by_name"):
        return db.get_team_by_name(parent_team_name)

    # Fallback: generic SQL fetcher.
    return db.fetchone(
        "SELECT id, name, lead_id, template_type, status FROM teams WHERE name = ?",
        (parent_team_name,),
    )


def validate_parent_reference(
    template: Template,
    parent_team_name: Optional[str],
    db: Any,
) -> Optional[str]:
    """Validate the parent reference for a template that has `requires`.

    Args:
        template: The child template that may require a parent.
        parent_team_name: The name of the parent team passed via `--under`,
            or None if no parent was specified.
        db: Database accessor; must answer either `get_team_by_name(name)` or
            `fetchone(sql, params)` returning a team-shaped dict.

    Returns:
        The parent team's `lead_id` (the manager of the new team-instance reports
        up to this worker), or None if the template has no `requires`.

    Raises:
        TemplateMissingParent: template requires a parent but none was provided.
        TemplateWrongParentType: parent exists but its template_type doesn't
            match any of template.requires (also raised when template_type is NULL,
            i.e. legacy pre-templates teams).
        TemplateParentTerminated: parent exists but is no longer active.
    """
    if not template.requires:
        return None

    if parent_team_name is None:
        raise TemplateMissingParent(template.name, template.requires)

    parent = _lookup_team(db, parent_team_name)
    if parent is None:
        # Treat "team doesn't exist" the same as "wrong type" — the operator's
        # next step is to pick a real team or spin one up.
        raise TemplateWrongParentType(
            template_name=template.name,
            parent_team_name=parent_team_name,
            parent_template_type=None,
            requires=template.requires,
        )

    # Tolerate both dict-shaped fakes and sqlite3.Row real rows.
    parent_template_type = parent["template_type"] if "template_type" in parent.keys() else None
    parent_status = parent["status"] if "status" in parent.keys() else "active"

    # Legacy NULL template_type → wrong-type with the friendly retag message.
    if parent_template_type is None:
        raise TemplateWrongParentType(
            template_name=template.name,
            parent_team_name=parent_team_name,
            parent_template_type=None,
            requires=template.requires,
        )

    # Type check first, status check second — type mismatch is a more specific
    # failure that doesn't depend on whether the team is currently active.
    if parent_template_type not in template.requires:
        raise TemplateWrongParentType(
            template_name=template.name,
            parent_team_name=parent_team_name,
            parent_template_type=parent_template_type,
            requires=template.requires,
        )

    if parent_status != "active":
        raise TemplateParentTerminated(parent_team_name)

    return parent["lead_id"] if "lead_id" in parent.keys() else None

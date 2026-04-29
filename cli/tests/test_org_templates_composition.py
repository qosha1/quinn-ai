"""
Failing unit tests for the parent-reference validator (single-edge,
reference-existing semantics — NO topological sort, NO cycle detection).

Spec sources (read these, not the bead description's older wording):
- quinn-ai-56yh §7: composition is reference-existing only. `launch_pod` (or
  any template with non-empty `requires`) MUST be invoked with `--under
  <existing-team-name>` and the parent team's `template_type` must match one
  of `template.requires`. No recursive auto-creation. No cycle detection.
- quinn-ai-iabn §C.2: `validate_parent_reference(template, parent_team_name,
  db) -> Optional[str]` lives at `cli.core.templates.composition`. Returns the
  parent team's `lead_id` (the manager the new team's manager will report to)
  on success. Raises `TemplateMissingParent`, `TemplateWrongParentType`, or
  `TemplateParentTerminated` (added to `shared/exceptions.py` per iabn §I).
- quinn-ai-iabn §K: existing teams created before the template_type column
  existed have NULL `template_type`. The validator must reject these as
  parents with a clear "this team predates templates; retag it first" message.

These tests fail today because `cli.core.templates` does not exist (and the
new exception classes are not yet on `shared.exceptions`). Imports happen
inside test bodies so pytest collects each test individually.
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helper builders — all import from cli.core.templates inside the function so
# import failures surface per-test (not at collection time).
# ---------------------------------------------------------------------------


def _make_template(
    *,
    name: str = "launch_pod",
    requires: tuple[str, ...] = (),
    description: str = "test template",
) -> Any:
    """Construct a minimal valid Template with one is_manager member.

    The exact member shape is irrelevant to parent-reference validation; we
    just need *a* Template instance with the right `requires` tuple.
    """
    from cli.core.templates.types import Template, TemplateMember

    members = (
        TemplateMember(role="tech-lead", count=1, cost=65, is_manager=True),
        TemplateMember(role="engineer", count=1, cost=50, is_manager=False),
    )
    return Template(
        name=name,
        description=description,
        members=members,
        requires=requires,
    )


def _make_db(
    *,
    teams_by_name: Optional[dict[str, dict[str, Any]]] = None,
) -> MagicMock:
    """Construct a fake Database that answers parent-team lookups.

    The validator looks up the parent team by name; iabn §C.2 doesn't pin the
    exact accessor, so the fake supports both shapes that are likely to land
    in impl: `db.get_team_by_name(name)` and a generic `db.fetchone(...)`
    fallback. Each entry in `teams_by_name` is a dict of team attrs
    (`id`, `name`, `lead_id`, `template_type`, `status`).
    """
    teams_by_name = teams_by_name or {}

    db = MagicMock()

    def _lookup(name: str) -> Optional[dict[str, Any]]:
        return teams_by_name.get(name)

    db.get_team_by_name.side_effect = _lookup
    # Some impls may use a generic fetchone with a SQL string + params; route
    # those by inspecting the params for the team name.
    def _fetchone_router(_sql: str, params: tuple[Any, ...]) -> Optional[dict[str, Any]]:
        if not params:
            return None
        return teams_by_name.get(params[0])

    db.fetchone.side_effect = _fetchone_router
    return db


# ---------------------------------------------------------------------------
# 1. No-requires templates: parent_team_name=None is fine, returns None.
# ---------------------------------------------------------------------------


class TestNoRequiresAcceptsNoParent:
    """Template with empty `requires` accepts no `parent_team_name` and the
    validator returns None (i.e. there is no parent manager to wire up)."""

    def test_empty_requires_with_no_parent_returns_none(self) -> None:
        from cli.core.templates.composition import validate_parent_reference

        tmpl = _make_template(name="product_team", requires=())
        db = _make_db()

        result = validate_parent_reference(tmpl, None, db)

        assert result is None


# ---------------------------------------------------------------------------
# 2. Non-empty requires + missing parent_team_name -> TemplateMissingParent
# ---------------------------------------------------------------------------


class TestMissingParent:
    """Template with non-empty `requires` AND no `parent_team_name` raises
    TemplateMissingParent."""

    def test_non_empty_requires_no_parent_raises_missing_parent(self) -> None:
        from cli.core.templates.composition import validate_parent_reference
        from shared.exceptions import TemplateMissingParent

        tmpl = _make_template(name="launch_pod", requires=("product_team",))
        db = _make_db()

        with pytest.raises(TemplateMissingParent) as exc_info:
            validate_parent_reference(tmpl, None, db)

        # Operator should see what was needed.
        msg = str(exc_info.value)
        assert "product_team" in msg or "launch_pod" in msg or "--under" in msg


# ---------------------------------------------------------------------------
# 3. Happy path — parent resolves, template_type matches, team active.
# ---------------------------------------------------------------------------


class TestHappyPath:
    """`parent_team_name` resolves to an existing active team whose
    `template_type` is in `template.requires` -> validator returns the parent
    team's `lead_id`."""

    def test_matching_active_parent_returns_lead_id(self) -> None:
        from cli.core.templates.composition import validate_parent_reference

        tmpl = _make_template(name="launch_pod", requires=("product_team",))
        db = _make_db(
            teams_by_name={
                "mobile-app": {
                    "id": "team-abc",
                    "name": "mobile-app",
                    "lead_id": "wrk-pm-1",
                    "template_type": "product_team",
                    "status": "active",
                }
            }
        )

        result = validate_parent_reference(tmpl, "mobile-app", db)

        assert result == "wrk-pm-1"


# ---------------------------------------------------------------------------
# 4. Wrong template_type -> TemplateWrongParentType
# ---------------------------------------------------------------------------


class TestWrongParentType:
    """`parent_team_name` resolves but its `template_type` is not in
    `template.requires` -> TemplateWrongParentType."""

    def test_mismatched_template_type_raises_wrong_parent_type(self) -> None:
        from cli.core.templates.composition import validate_parent_reference
        from shared.exceptions import TemplateWrongParentType

        tmpl = _make_template(name="launch_pod", requires=("product_team",))
        db = _make_db(
            teams_by_name={
                "ops-squad": {
                    "id": "team-xyz",
                    "name": "ops-squad",
                    "lead_id": "wrk-sre-1",
                    "template_type": "incident_response_squad",  # not what we need
                    "status": "active",
                }
            }
        )

        with pytest.raises(TemplateWrongParentType) as exc_info:
            validate_parent_reference(tmpl, "ops-squad", db)

        msg = str(exc_info.value)
        # Operator should see required vs actual.
        assert "product_team" in msg
        assert "incident_response_squad" in msg or "ops-squad" in msg


# ---------------------------------------------------------------------------
# 5. Terminated/inactive parent -> TemplateParentTerminated
# ---------------------------------------------------------------------------


class TestParentTerminated:
    """`parent_team_name` resolves but the team is terminated/inactive ->
    TemplateParentTerminated."""

    def test_terminated_parent_raises_parent_terminated(self) -> None:
        from cli.core.templates.composition import validate_parent_reference
        from shared.exceptions import TemplateParentTerminated

        tmpl = _make_template(name="launch_pod", requires=("product_team",))
        db = _make_db(
            teams_by_name={
                "old-mobile-app": {
                    "id": "team-old",
                    "name": "old-mobile-app",
                    "lead_id": "wrk-pm-2",
                    "template_type": "product_team",  # right type
                    "status": "terminated",  # but no longer active
                }
            }
        )

        with pytest.raises(TemplateParentTerminated) as exc_info:
            validate_parent_reference(tmpl, "old-mobile-app", db)

        msg = str(exc_info.value)
        assert "old-mobile-app" in msg or "terminated" in msg.lower()


# ---------------------------------------------------------------------------
# 6. Legacy team with NULL template_type -> TemplateWrongParentType with a
#    clear "predates templates; retag it first" message.
# ---------------------------------------------------------------------------


class TestLegacyParentNullTemplateType:
    """`parent_team_name` resolves but the team has NULL `template_type`
    (created before the templates feature shipped). Per iabn §K, the
    validator rejects this as TemplateWrongParentType with a message guiding
    the operator to retag the team first."""

    def test_legacy_null_template_type_raises_wrong_parent_type(self) -> None:
        from cli.core.templates.composition import validate_parent_reference
        from shared.exceptions import TemplateWrongParentType

        tmpl = _make_template(name="launch_pod", requires=("product_team",))
        db = _make_db(
            teams_by_name={
                "legacy-team": {
                    "id": "team-legacy",
                    "name": "legacy-team",
                    "lead_id": "wrk-old-pm",
                    "template_type": None,  # legacy: predates templates
                    "status": "active",
                }
            }
        )

        with pytest.raises(TemplateWrongParentType) as exc_info:
            validate_parent_reference(tmpl, "legacy-team", db)

        msg = str(exc_info.value).lower()
        # Operator should see actionable guidance, not just a type mismatch.
        assert "predates" in msg or "retag" in msg or "legacy" in msg


# ---------------------------------------------------------------------------
# Smoke-level type assertion: the new exception classes are exposed where
# the design pins them. iabn §I adds these to `shared/exceptions.py`.
# ---------------------------------------------------------------------------


def test_template_exceptions_exposed_on_shared_exceptions() -> None:
    from shared.exceptions import (
        TemplateMissingParent,
        TemplateParentTerminated,
        TemplateWrongParentType,
    )

    for exc, name in (
        (TemplateMissingParent, "TemplateMissingParent"),
        (TemplateWrongParentType, "TemplateWrongParentType"),
        (TemplateParentTerminated, "TemplateParentTerminated"),
    ):
        assert exc is not None, f"{name} missing from shared.exceptions"
        assert issubclass(exc, Exception), f"{name} must subclass Exception"

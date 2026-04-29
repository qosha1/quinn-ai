"""
Failing unit tests for the org-templates YAML schema parser & validator.

Spec sources (read these, not the bead description — the bead description's
mentions of reserved-name lists and a closed allowed-roles registry are
secondary; the iabn system design supersedes):
- quinn-ai-56yh: user requirements (5 v0 templates, free-form role strings,
  per-member cost 0-100 passed through to existing `qn org hire --cost`,
  reference-existing composition, NO budget block on templates).
- quinn-ai-iabn §A: full templates.yaml schema — required fields per template
  (name, description, members), required fields per member (role, count, cost),
  exactly-one `is_manager: true` per template, optional channel block,
  optional `requires` (list of template names), optional `initial_okrs`,
  optional `ttl_hours`.
- quinn-ai-iabn §B: in-memory data model (`Template`, `TemplateMember`,
  `TemplateRegistry`) lives in `cli.core.templates.types`.

Composition is reference-existing only: `requires` referencing an unknown
template name is rejected at LOAD time so the orchestrator never sees a
template whose dep won't resolve.

These tests fail today because `cli.core.templates` does not exist. Imports
happen inside test bodies (not at module top) so pytest can still collect each
test individually and report a per-test ImportError, giving a proper
failing-test count. Phase-4 implementation work makes them green.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _write_templates_yaml(org_path: Path, body: str) -> Path:
    """Write templates.yaml under <org_path>/config/ and return its path."""
    config_dir = org_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "templates.yaml"
    target.write_text(body)
    return target


@pytest.fixture
def org_path(tmp_path: Path) -> Path:
    """A throwaway org root."""
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Minimal-valid round-trip + the full 5-template default catalog parses
# ---------------------------------------------------------------------------


class TestMinimalRoundTrip:
    """A minimal valid templates.yaml parses into a TemplateRegistry with the
    right Template objects."""

    def test_minimal_valid_yaml_round_trips_to_registry(
        self, org_path: Path
    ) -> None:
        from cli.core.templates import loader as templates_loader
        from cli.core.templates.types import (
            Template,
            TemplateMember,
            TemplateRegistry,
        )

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: product_team
    description: "Standard product team — PM-led, ships features."
    members:
      - role: pm
        count: 1
        is_manager: true
        cost: 60
      - role: engineer
        count: 2
        cost: 50
""",
        )

        registry: TemplateRegistry = templates_loader.load_templates(org_path)

        assert isinstance(registry, TemplateRegistry)
        assert registry.version == 1
        assert len(registry.templates) == 1

        tmpl: Template = registry.templates[0]
        assert isinstance(tmpl, Template)
        assert tmpl.name == "product_team"
        assert "PM-led" in tmpl.description
        assert len(tmpl.members) == 2

        pm: TemplateMember = tmpl.members[0]
        assert isinstance(pm, TemplateMember)
        assert pm.role == "pm"
        assert pm.count == 1
        assert pm.is_manager is True
        assert pm.cost == 60

        eng: TemplateMember = tmpl.members[1]
        assert eng.role == "engineer"
        assert eng.count == 2
        assert eng.is_manager is False  # default
        assert eng.cost == 50

    def test_all_five_v0_templates_parse(self, org_path: Path) -> None:
        """All 5 v0 templates from 56yh §1 parse from a sample fixture."""
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: product_team
    description: "Standard product team — PM-led, ships features."
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
      - {role: engineer, count: 2, cost: 50}
      - {role: designer, count: 1, cost: 45}
      - {role: qa, count: 1, cost: 40}
  - name: data_team
    description: "Data engineering + analytics."
    members:
      - {role: data-eng, count: 1, is_manager: true, cost: 60}
      - {role: data-eng, count: 1, cost: 50}
      - {role: analyst, count: 1, cost: 45}
      - {role: ml-eng, count: 1, cost: 55}
  - name: launch_pod
    description: "Cross-functional launch pod under a product team."
    members:
      - {role: tech-lead, count: 1, is_manager: true, cost: 65}
      - {role: engineer, count: 1, cost: 50}
      - {role: designer, count: 1, cost: 45}
      - {role: qa, count: 1, cost: 40}
    requires: [product_team]
  - name: incident_response_squad
    description: "Time-bounded incident response squad."
    members:
      - {role: incident-commander, count: 1, is_manager: true, cost: 70}
      - {role: sre, count: 2, cost: 55}
      - {role: comms, count: 1, cost: 40}
    ttl_hours: 72
  - name: research_pod
    description: "Research pod — investigates, prototypes, hands off."
    members:
      - {role: research-lead, count: 1, is_manager: true, cost: 65}
      - {role: researcher, count: 2, cost: 50}
      - {role: engineer, count: 1, cost: 50}
""",
        )

        registry = templates_loader.load_templates(org_path)
        names = {t.name for t in registry.templates}

        assert names == {
            "product_team",
            "data_team",
            "launch_pod",
            "incident_response_squad",
            "research_pod",
        }
        # launch_pod's `requires` round-trips
        launch_pod = next(t for t in registry.templates if t.name == "launch_pod")
        assert launch_pod.requires == ("product_team",)
        # incident_response_squad's `ttl_hours` round-trips
        irs = next(
            t for t in registry.templates if t.name == "incident_response_squad"
        )
        assert irs.ttl_hours == 72


# ---------------------------------------------------------------------------
# 2. is_manager validation — exactly one per template
# ---------------------------------------------------------------------------


class TestIsManagerValidation:
    """Per iabn §A.2: exactly one member with is_manager: true per template."""

    def test_zero_managers_rejected(self, org_path: Path) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: bad_team
    description: "no manager flagged"
    members:
      - {role: engineer, count: 2, cost: 50}
      - {role: qa, count: 1, cost: 40}
""",
        )

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value).lower()
        # Error must reference is_manager / manager somehow.
        assert "manager" in msg or "is_manager" in msg

    def test_two_managers_rejected(self, org_path: Path) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: too_many_chefs
    description: "two managers"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
      - {role: tech-lead, count: 1, is_manager: true, cost: 65}
      - {role: engineer, count: 2, cost: 50}
""",
        )

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value).lower()
        assert "manager" in msg or "is_manager" in msg
        # The template name is helpful for operators.
        assert "too_many_chefs" in str(exc_info.value)

    def test_exactly_one_manager_accepted(self, org_path: Path) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: ok_team
    description: "exactly one manager"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
      - {role: engineer, count: 2, cost: 50}
""",
        )

        registry = templates_loader.load_templates(org_path)
        tmpl = registry.templates[0]
        managers = [m for m in tmpl.members if m.is_manager]
        assert len(managers) == 1
        assert managers[0].role == "pm"


# ---------------------------------------------------------------------------
# 3. Required-field validation — each missing field cited by name
# ---------------------------------------------------------------------------


class TestRequiredFields:
    """Per iabn §A.1: name, description, members (with role/count/cost) are
    required. Missing fields are rejected with field-citing errors."""

    @pytest.mark.parametrize(
        "missing_field,yaml_body",
        [
            (
                "name",
                """
version: 1
templates:
  - description: "no name"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
""",
            ),
            (
                "description",
                """
version: 1
templates:
  - name: no_desc
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
""",
            ),
            (
                "members",
                """
version: 1
templates:
  - name: no_members
    description: "missing members list"
""",
            ),
            (
                "role",
                """
version: 1
templates:
  - name: bad_member
    description: "member without role"
    members:
      - {count: 1, is_manager: true, cost: 60}
""",
            ),
            (
                "count",
                """
version: 1
templates:
  - name: bad_member
    description: "member without count"
    members:
      - {role: pm, is_manager: true, cost: 60}
""",
            ),
            (
                "cost",
                """
version: 1
templates:
  - name: bad_member
    description: "member without cost"
    members:
      - {role: pm, count: 1, is_manager: true}
""",
            ),
        ],
    )
    def test_missing_required_field_rejected(
        self, org_path: Path, missing_field: str, yaml_body: str
    ) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(org_path, yaml_body)

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value).lower()
        # Error must name the offending field; lenient on exact phrasing.
        assert missing_field in msg


# ---------------------------------------------------------------------------
# 4. Duplicate template names rejected
# ---------------------------------------------------------------------------


class TestDuplicateNames:
    """Two templates with the same `name` within the same file -> error."""

    def test_duplicate_template_names_rejected(self, org_path: Path) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: my_team
    description: "first"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
  - name: my_team
    description: "second with same name"
    members:
      - {role: tech-lead, count: 1, is_manager: true, cost: 65}
""",
        )

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value).lower()
        assert "duplicate" in msg or "my_team" in msg


# ---------------------------------------------------------------------------
# 5. Strict schema — unknown YAML keys rejected (fail-closed)
# ---------------------------------------------------------------------------


class TestStrictSchema:
    """Unknown keys at template or member level are rejected so typos and
    speculative future-fields surface immediately rather than being silently
    dropped."""

    def test_unknown_top_level_template_key_rejected(
        self, org_path: Path
    ) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: with_typo
    description: "has unknown key"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
    budget: 1000   # NOT a valid template key — templates carry no budget block
""",
        )

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value).lower()
        assert "budget" in msg or "unknown" in msg or "unexpected" in msg

    def test_unknown_member_level_key_rejected(self, org_path: Path) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: ok_top
    description: "member has typo'd key"
    members:
      - role: pm
        count: 1
        is_manager: true
        cost: 60
        seniority: senior   # NOT a valid member key
""",
        )

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value).lower()
        assert "seniority" in msg or "unknown" in msg or "unexpected" in msg


# ---------------------------------------------------------------------------
# 6. Cost-value validation — must be int in [0, 100]
# ---------------------------------------------------------------------------


class TestCostValidation:
    """Per iabn §A: cost is a required int in 0-100. Negatives, >100, and
    non-int values are rejected."""

    @pytest.mark.parametrize(
        "bad_cost_yaml",
        [
            "cost: -1",
            "cost: 101",
            "cost: 9999",
            'cost: "60"',  # string, not int
            "cost: 60.5",  # float, not int
            "cost: true",  # bool
        ],
    )
    def test_invalid_cost_rejected(
        self, org_path: Path, bad_cost_yaml: str
    ) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            f"""
version: 1
templates:
  - name: bad_cost
    description: "cost is invalid"
    members:
      - role: pm
        count: 1
        is_manager: true
        {bad_cost_yaml}
""",
        )

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value).lower()
        assert "cost" in msg


# ---------------------------------------------------------------------------
# 7. `requires` referencing unknown template name -> rejected at LOAD time
# ---------------------------------------------------------------------------


class TestRequiresReferentialIntegrity:
    """Per iabn §C.2: composition is reference-existing only and `requires`
    referencing an unknown template name is rejected at LOAD time so the
    orchestrator never sees a template whose dep won't resolve."""

    def test_requires_unknown_template_name_rejected_at_load(
        self, org_path: Path
    ) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: launch_pod
    description: "requires a template that doesn't exist in this file"
    members:
      - {role: tech-lead, count: 1, is_manager: true, cost: 65}
      - {role: engineer, count: 1, cost: 50}
    requires: [phantom_team]   # not declared anywhere in this file
""",
        )

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value)
        # Operator should see the missing template name verbatim.
        assert "phantom_team" in msg

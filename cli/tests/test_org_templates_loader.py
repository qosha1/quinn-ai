"""
Failing unit tests for the org-templates loader.

Spec sources (read these, not the bead description — the bead description's
"merge default templates with org-local templates.yaml" wording is stale; the
iabn design supersedes with a simpler default-fallback contract):
- quinn-ai-56yh §1: 5 v0 templates ship as the default catalog (`product_team`,
  `data_team`, `launch_pod`, `incident_response_squad`, `research_pod`).
- quinn-ai-iabn §A.4: defaults file lives at
  `cli/config/default_team_templates.yaml`. When `<org_path>/config/templates.yaml`
  is absent, `load_templates(org_path)` falls back to the bundled defaults —
  NOT empty, NOT an error.
- quinn-ai-iabn §C.1: `load_templates(org_path: Path) -> TemplateRegistry`.
  Fails closed on YAML parse / schema-validation errors with a clear
  path-citing message.

These tests fail today because `cli.core.templates` does not exist. Imports
happen inside test bodies so pytest can collect each test individually and
report per-test ImportError rather than a single collection error.
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
# 1. Default-catalog fallback when no templates.yaml exists
# ---------------------------------------------------------------------------


class TestDefaultCatalogFallback:
    """`load_templates(org_path)` with no templates.yaml falls back to the
    bundled default catalog (5 templates per 56yh §1) — NOT empty, NOT an
    error."""

    def test_missing_templates_yaml_loads_default_catalog(
        self, org_path: Path
    ) -> None:
        from cli.core.templates import loader as templates_loader
        from cli.core.templates.types import TemplateRegistry

        # Note: org_path has no config/templates.yaml.
        registry = templates_loader.load_templates(org_path)

        assert isinstance(registry, TemplateRegistry)
        # The default catalog has 5 templates per quinn-ai-56yh §1.
        assert len(registry.templates) == 5, (
            "expected the bundled 5-template default catalog when no "
            "templates.yaml is present"
        )

    def test_default_catalog_includes_named_v0_templates(
        self, org_path: Path
    ) -> None:
        """Per 56yh §1, the default catalog includes specific named templates."""
        from cli.core.templates import loader as templates_loader

        registry = templates_loader.load_templates(org_path)
        names = {t.name for t in registry.templates}

        for expected in (
            "product_team",
            "data_team",
            "launch_pod",
            "incident_response_squad",
            "research_pod",
        ):
            assert expected in names, (
                f"expected {expected} in bundled default template catalog"
            )


# ---------------------------------------------------------------------------
# 2. Malformed YAML -> descriptive fail-closed error
# ---------------------------------------------------------------------------


class TestMalformedYaml:
    """Malformed YAML raises a descriptive error citing file path + parse
    location (fail-closed)."""

    def test_malformed_yaml_raises_descriptive_error(
        self, org_path: Path
    ) -> None:
        from cli.core.templates import loader as templates_loader

        target = _write_templates_yaml(
            org_path,
            "version: 1\ntemplates:\n  - name: broken\n    description: [unclosed\n",
        )

        with pytest.raises(Exception) as exc_info:
            templates_loader.load_templates(org_path)

        msg = str(exc_info.value)
        # Path to the offending file should appear in the error.
        assert str(target) in msg or "templates.yaml" in msg
        # Parse-level signal should be present (line/column or 'parse'/'yaml').
        lower = msg.lower()
        assert any(token in lower for token in ("line", "yaml", "parse", "column"))


# ---------------------------------------------------------------------------
# 3. Loader idempotency
# ---------------------------------------------------------------------------


class TestLoaderIdempotency:
    """Calling load_templates twice with the same input yields equal
    TemplateRegistry objects."""

    def test_loader_is_idempotent(self, org_path: Path) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: alpha_team
    description: "first"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
      - {role: engineer, count: 1, cost: 50}
  - name: beta_team
    description: "second"
    members:
      - {role: tech-lead, count: 1, is_manager: true, cost: 65}
      - {role: engineer, count: 2, cost: 50}
""",
        )

        reg_a = templates_loader.load_templates(org_path)
        reg_b = templates_loader.load_templates(org_path)

        assert reg_a == reg_b
        assert tuple(t.name for t in reg_a.templates) == tuple(
            t.name for t in reg_b.templates
        )


# ---------------------------------------------------------------------------
# 4. Deterministic sort order — by template name
# ---------------------------------------------------------------------------


class TestDeterministicOrder:
    """Templates are sorted deterministically by name in the returned registry,
    so callers (CLI listings, briefing renders) get a stable order."""

    def test_templates_sorted_by_name(self, org_path: Path) -> None:
        from cli.core.templates import loader as templates_loader

        _write_templates_yaml(
            org_path,
            """
version: 1
templates:
  - name: zebra_team
    description: "z"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
  - name: alpha_team
    description: "a"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
  - name: middle_team
    description: "m"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
""",
        )

        registry = templates_loader.load_templates(org_path)
        observed_names = [t.name for t in registry.templates]

        assert observed_names == sorted(observed_names), (
            "templates must come out sorted by name for deterministic order"
        )
        assert observed_names == ["alpha_team", "middle_team", "zebra_team"]


# ---------------------------------------------------------------------------
# 5. Empty `templates: []` is valid (operator's explicit choice)
# ---------------------------------------------------------------------------


class TestExplicitlyEmptyTemplates:
    """`version: 1` with `templates: []` is valid and yields a TemplateRegistry
    with zero templates — operator turned the catalog off explicitly. This is
    NOT the same as a missing file, which falls back to the bundled defaults.
    """

    def test_empty_templates_yields_zero_template_registry(
        self, org_path: Path
    ) -> None:
        from cli.core.templates import loader as templates_loader
        from cli.core.templates.types import TemplateRegistry

        _write_templates_yaml(
            org_path,
            """
version: 1
templates: []
""",
        )

        registry = templates_loader.load_templates(org_path)

        assert isinstance(registry, TemplateRegistry)
        assert registry.version == 1
        assert registry.templates == ()  # no templates, no error
        # Critical: explicit empty list must NOT silently expand to the
        # 5-template default fallback.
        assert len(registry.templates) == 0


# ---------------------------------------------------------------------------
# Bonus: source_path round-trips when a file is present
# ---------------------------------------------------------------------------


def test_loader_records_source_path_when_yaml_present(tmp_path: Path) -> None:
    """When templates.yaml exists, the resulting TemplateRegistry remembers
    its origin (per iabn §B: `source_path` is the absolute path to the
    templates.yaml that produced this registry)."""
    from cli.core.templates import loader as templates_loader

    org_path = tmp_path
    target = _write_templates_yaml(
        org_path,
        """
version: 1
templates:
  - name: only_team
    description: "one"
    members:
      - {role: pm, count: 1, is_manager: true, cost: 60}
""",
    )

    registry = templates_loader.load_templates(org_path)

    assert hasattr(registry, "source_path")
    assert (
        str(target) == registry.source_path
        or str(target.resolve()) == registry.source_path
    )

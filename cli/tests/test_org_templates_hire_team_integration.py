"""
Failing integration tests for `TemplateOrchestrator.hire_team()` end-to-end.

Spec sources (read these first — the bead description for quinn-ai-7xu5
predates the system design and uses stale `--budget` / `delegate-authority`
wording. Live spec:

- quinn-ai-56yh §1, §7, §8 — 5 v0 templates; reference-existing composition;
  single-CLI-call hire UX with `--override <role>:<count>` and
  `--override <role>:cost=<n>` parser; rollback on partial failure.
- quinn-ai-iabn §A — templates.yaml schema (members[] with role/count/cost,
  channel.name_template, requires[], initial_okrs[], ttl_hours).
- quinn-ai-iabn §B — `Template`, `TemplateMember`, `ChannelSpec`,
  `TemplateRegistry`, `HireTeamResult` dataclasses (in cli.core.templates.types).
- quinn-ai-iabn §C.3 / §D — `TemplateOrchestrator.hire_team(...)` 14-step
  atomic sequence with rollback. Returns `HireTeamResult` whose
  `rolled_back: bool` field flags partial-failure rollback.
- quinn-ai-iabn §E — schema migration adds `template_type`, `ttl_hours`,
  `ttl_started_at` columns to the teams table.
- quinn-ai-iabn §F — `qn org hire-team` Click command; `qn org templates`
  subgroup (list / show / validate).
- quinn-ai-u0h2 §3 — DI: orchestrator takes `(ctx, db, registry)`; tests
  inject fakes directly without the click decorator-context machinery.
- quinn-ai-u0h2 §4 — reuse-map: real `create_team`, `create_channel`,
  `add_team_member` (existing in `cli.core.queries.{team,channel}`); fakes
  for `hire_worker`, `fire_worker`, `create_okr`, `close_okr` (these are
  Phase-4 extractions — not yet implemented).
- quinn-ai-u0h2 §6 — `--override engineer:3` → size override;
  `--override engineer:cost=70` → cost override.
- quinn-ai-u0h2 §11 — fakes are functions (NOT classes) bound at module
  level on `cli.core.templates.orchestrator._helpers`, easy to monkey-patch.

These tests fail today because:
  - `cli.core.templates` does not exist.
  - The teams-table migration adding `template_type` / `ttl_hours` /
    `ttl_started_at` has not landed.
  - `hire_worker` / `fire_worker` / `create_okr` / `close_okr` programmatic
    helpers haven't been extracted yet.

Imports happen inside test bodies so failures surface per-test. Pattern
matches `cli/tests/test_board_rules_engine.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Templates YAML used across tests (5-member product_team; 4-member launch_pod)
# ---------------------------------------------------------------------------

_TEMPLATES_YAML = """\
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
      - role: designer
        count: 1
        cost: 45
      - role: qa
        count: 1
        cost: 40
    channel:
      auto_create: true
      name_template: "product-{team_name}"
    requires: []
    initial_okrs: []
  - name: launch_pod
    description: "Launch pod — references an existing product_team via --under."
    members:
      - role: tech-lead
        count: 1
        is_manager: true
        cost: 60
      - role: engineer
        count: 1
        cost: 50
      - role: designer
        count: 1
        cost: 45
      - role: qa
        count: 1
        cost: 40
    channel:
      auto_create: true
      name_template: "launch-{team_name}"
    requires: [product_team]
    initial_okrs: []
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def org_db(tmp_path: Path):
    """A fresh sqlite DB at tmp_path with the templates-fields migration applied.

    The migration (add `template_type`, `ttl_hours`, `ttl_started_at` columns
    to the teams table) is part of the BOARD-TPL impl — this fixture WILL fail
    today on either:
      (a) ImportError on `cli.core.templates` (the migration helper lives
          alongside the orchestrator code), OR
      (b) OperationalError when SELECTing template_type from a pre-migration
          schema.
    Both failures are correct test-time failures.
    """
    from cli.core.db import init_database, get_org_db_path
    from cli.core.templates.migration import apply_template_fields_migration  # noqa: F401

    db_path = get_org_db_path(tmp_path)
    db = init_database(db_path)
    apply_template_fields_migration(db)
    yield db, tmp_path
    db.close()


@pytest.fixture
def registry(tmp_path: Path):
    """A TemplateRegistry loaded from a templates.yaml on disk."""
    from cli.core.templates.loader import load_templates

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "templates.yaml").write_text(_TEMPLATES_YAML)
    return load_templates(tmp_path)


@pytest.fixture
def fake_helpers(monkeypatch):
    """Replace the orchestrator's hire_worker/fire_worker/create_okr/close_okr
    callables with fakes. Per u0h2 §11 these are module-level function bindings
    on `cli.core.templates.orchestrator._helpers`, so monkeypatch can swap them.

    Returns a dict mapping helper name → MagicMock so tests can assert on them.
    """
    from cli.core.templates import orchestrator as orch_module

    fakes: dict[str, MagicMock] = {
        "hire_worker": MagicMock(side_effect=_default_fake_hire_worker),
        "fire_worker": MagicMock(),
        "create_okr": MagicMock(side_effect=_default_fake_create_okr),
        "close_okr": MagicMock(),
    }
    for name, fake in fakes.items():
        monkeypatch.setattr(orch_module._helpers, name, fake)
    return fakes


def _default_fake_hire_worker(db, ctx, *, name, role, manager_id, cost) -> Any:
    """Stand-in hire_worker that inserts a worker row directly via create_worker."""
    from cli.core.queries.worker import create_worker

    # Use the org's first team for the worker's team_id (the orchestrator
    # will move them to the right team via add_team_member afterward).
    row = db.fetchone("SELECT id FROM teams ORDER BY created_at LIMIT 1")
    team_id = row["id"] if row else "team-default"
    return create_worker(
        db,
        name=name,
        role=role,
        team_id=team_id,
        cost=cost,
        manager_id=manager_id,
    )


def _default_fake_create_okr(db, ctx, *, title, description, owner_id, **_kw) -> Any:
    """Stand-in create_okr that returns a sentinel id."""
    return f"okr-{owner_id}-{abs(hash(title)) % 100000}"


def _seed_ceo(db) -> str:
    """Insert a CEO worker so hire-team has a manager_id to point reports-to at."""
    from cli.core.queries.team import create_team
    from cli.core.queries.worker import create_worker

    team = create_team(db, name="exec", auto_create_channel=False)
    ceo = create_worker(
        db,
        name="Alice",
        role="ceo",
        team_id=team.id,
        cost=80,
        manager_id=None,
    )
    return ceo.id


# ===========================================================================
# Test 1 — Happy path: hire_team(product_team) creates 1 team + 1 channel +
#                      5 workers; HireTeamResult.rolled_back=False.
# ===========================================================================


class TestHireTeamHappyPath:
    """Smoke test for the 14-step orchestration sequence."""

    def test_product_team_creates_5_workers_team_and_channel(
        self, org_db, registry, fake_helpers
    ) -> None:
        from cli.core.templates.orchestrator import TemplateOrchestrator

        db, org_path = org_db
        ceo_id = _seed_ceo(db)

        orch = TemplateOrchestrator(ctx=MagicMock(), db=db, registry=registry)
        result = orch.hire_team(
            template_name="product_team",
            team_name="mobile",
            manager_id=ceo_id,
        )

        # Result shape.
        assert result.rolled_back is False
        assert len(result.worker_ids) == 5  # 1 PM + 2 engineers + 1 designer + 1 QA
        assert result.team_id is not None
        assert result.channel_id is not None

        # DB state.
        team_row = db.fetchone(
            "SELECT id, name, template_type FROM teams WHERE name = ?", ("mobile",)
        )
        assert team_row is not None
        assert team_row["template_type"] == "product_team"

        # Channel exists with the expected derived name.
        channel_row = db.fetchone(
            "SELECT id, name FROM channels WHERE id = ?", (result.channel_id,)
        )
        assert channel_row is not None
        assert channel_row["name"] == "product-mobile"

        # Workers in the new team.
        worker_count_row = db.fetchone(
            "SELECT COUNT(*) AS c FROM workers WHERE id IN ({})".format(
                ",".join("?" * len(result.worker_ids))
            ),
            tuple(result.worker_ids),
        )
        assert worker_count_row["c"] == 5


# ===========================================================================
# Test 2 — Size override: --override engineer:3 → 6 total workers.
# ===========================================================================


class TestHireTeamSizeOverride:
    """`--override engineer:3` adds two extra engineers (4 default → 6 total)."""

    def test_engineer_size_override_3_yields_6_workers(
        self, org_db, registry, fake_helpers
    ) -> None:
        from cli.core.templates.orchestrator import TemplateOrchestrator

        db, _ = org_db
        ceo_id = _seed_ceo(db)

        orch = TemplateOrchestrator(ctx=MagicMock(), db=db, registry=registry)
        result = orch.hire_team(
            template_name="product_team",
            team_name="growth",
            manager_id=ceo_id,
            size_overrides={"engineer": 3},
        )

        # 1 PM + 3 engineers + 1 designer + 1 QA = 6
        assert len(result.worker_ids) == 6
        assert result.rolled_back is False

        # Verify exactly 3 workers with role=engineer were created.
        engineer_count = db.fetchone(
            "SELECT COUNT(*) AS c FROM workers WHERE role = ? AND id IN ({})".format(
                ",".join("?" * len(result.worker_ids))
            ),
            ("engineer",) + tuple(result.worker_ids),
        )["c"]
        assert engineer_count == 3


# ===========================================================================
# Test 3 — Cost override: --override engineer:cost=70 → engineers hired at cost 70.
# ===========================================================================


class TestHireTeamCostOverride:
    """`--override engineer:cost=70` flows through to the per-hire cost."""

    def test_engineer_cost_override_70_persists_in_db(
        self, org_db, registry, fake_helpers
    ) -> None:
        from cli.core.templates.orchestrator import TemplateOrchestrator

        db, _ = org_db
        ceo_id = _seed_ceo(db)

        orch = TemplateOrchestrator(ctx=MagicMock(), db=db, registry=registry)
        result = orch.hire_team(
            template_name="product_team",
            team_name="payments",
            manager_id=ceo_id,
            cost_overrides={"engineer": 70},
        )

        assert result.rolled_back is False

        # All workers with role=engineer in the new team were hired at cost=70.
        rows = db.fetchall(
            "SELECT cost FROM workers WHERE role = ? AND id IN ({})".format(
                ",".join("?" * len(result.worker_ids))
            ),
            ("engineer",) + tuple(result.worker_ids),
        )
        assert rows, "expected at least one engineer in the result set"
        for row in rows:
            assert row["cost"] == 70, f"engineer cost not overridden: {row['cost']}"


# ===========================================================================
# Test 4 — launch_pod requires product_team:
#          - missing --under raises TemplateMissingParent.
#          - --under=mobile (existing product_team) succeeds.
# ===========================================================================


class TestHireTeamComposition:
    """Reference-existing composition: --under is required when requires non-empty."""

    def test_launch_pod_without_under_raises_template_missing_parent(
        self, org_db, registry, fake_helpers
    ) -> None:
        from cli.core.templates.orchestrator import TemplateOrchestrator
        from shared.exceptions import TemplateMissingParent

        db, _ = org_db
        ceo_id = _seed_ceo(db)

        orch = TemplateOrchestrator(ctx=MagicMock(), db=db, registry=registry)
        with pytest.raises(TemplateMissingParent):
            orch.hire_team(
                template_name="launch_pod",
                team_name="auth-redesign",
                manager_id=ceo_id,
                # parent_team_name omitted → must raise.
            )

    def test_launch_pod_with_existing_product_team_succeeds(
        self, org_db, registry, fake_helpers
    ) -> None:
        from cli.core.templates.orchestrator import TemplateOrchestrator

        db, _ = org_db
        ceo_id = _seed_ceo(db)

        orch = TemplateOrchestrator(ctx=MagicMock(), db=db, registry=registry)
        # First, set up a real product_team called "mobile".
        parent_result = orch.hire_team(
            template_name="product_team",
            team_name="mobile",
            manager_id=ceo_id,
        )
        assert parent_result.rolled_back is False

        # Now create a launch_pod under it.
        child_result = orch.hire_team(
            template_name="launch_pod",
            team_name="auth-redesign",
            manager_id=ceo_id,
            parent_team_name="mobile",
        )
        assert child_result.rolled_back is False
        assert len(child_result.worker_ids) == 4  # tech-lead + engineer + designer + qa

        # Parent linkage stored on the child team row.
        child_row = db.fetchone(
            "SELECT parent_team_id FROM teams WHERE id = ?", (child_result.team_id,)
        )
        assert child_row["parent_team_id"] == parent_result.team_id


# ===========================================================================
# Test 5 — Channel collision: pre-existing channel with the derived name
#                              raises ChannelNameCollision; no team/worker created.
# ===========================================================================


class TestHireTeamChannelCollision:
    """Pre-validate channel collision per iabn §D step 4."""

    def test_channel_collision_raises_and_leaves_db_unchanged(
        self, org_db, registry, fake_helpers
    ) -> None:
        from cli.core.queries.channel import create_channel
        from cli.core.templates.orchestrator import TemplateOrchestrator
        from shared.exceptions import ChannelNameCollision

        db, _ = org_db
        ceo_id = _seed_ceo(db)

        # Pre-create a channel with the name the template will derive.
        create_channel(db, name="product-mobile", channel_type="general")

        # Baseline counts.
        baseline_teams = db.fetchone("SELECT COUNT(*) AS c FROM teams")["c"]
        baseline_workers = db.fetchone("SELECT COUNT(*) AS c FROM workers")["c"]

        orch = TemplateOrchestrator(ctx=MagicMock(), db=db, registry=registry)
        with pytest.raises(ChannelNameCollision):
            orch.hire_team(
                template_name="product_team",
                team_name="mobile",
                manager_id=ceo_id,
            )

        # No partial state.
        assert db.fetchone("SELECT COUNT(*) AS c FROM teams")["c"] == baseline_teams
        assert db.fetchone("SELECT COUNT(*) AS c FROM workers")["c"] == baseline_workers


# ===========================================================================
# Test 6 — Rollback: hire_worker raises on the 3rd hire → all prior hires,
#                    team, channel, OKRs are reverted; DB returns to baseline;
#                    HireTeamResult.rolled_back=True.
# ===========================================================================


class TestHireTeamRollbackOnPartialFailure:
    """Rollback strategy from iabn §D.1."""

    def test_third_hire_failure_reverts_team_channel_and_workers(
        self, org_db, registry, fake_helpers, monkeypatch
    ) -> None:
        from cli.core.templates import orchestrator as orch_module
        from cli.core.templates.orchestrator import TemplateOrchestrator

        db, _ = org_db
        ceo_id = _seed_ceo(db)

        # Baseline counts BEFORE attempting hire-team.
        baseline_teams = db.fetchone("SELECT COUNT(*) AS c FROM teams")["c"]
        baseline_workers = db.fetchone("SELECT COUNT(*) AS c FROM workers")["c"]
        baseline_channels = db.fetchone("SELECT COUNT(*) AS c FROM channels")["c"]

        # Wire a poison-pill hire_worker: succeeds twice, raises on the 3rd call.
        call_count = {"n": 0}

        def poison_hire_worker(db, ctx, *, name, role, manager_id, cost):
            call_count["n"] += 1
            if call_count["n"] == 3:
                raise RuntimeError("simulated session-spawn failure on 3rd hire")
            return _default_fake_hire_worker(
                db, ctx, name=name, role=role, manager_id=manager_id, cost=cost
            )

        monkeypatch.setattr(orch_module._helpers, "hire_worker", poison_hire_worker)

        orch = TemplateOrchestrator(ctx=MagicMock(), db=db, registry=registry)
        result = orch.hire_team(
            template_name="product_team",
            team_name="ill-fated",
            manager_id=ceo_id,
        )

        # Result flags rollback.
        assert result.rolled_back is True
        assert result.failure_reason is not None

        # DB row counts back to baseline (all 2 successful hires + team + channel reverted).
        assert (
            db.fetchone("SELECT COUNT(*) AS c FROM teams")["c"] == baseline_teams
        ), "team row not rolled back"
        assert (
            db.fetchone("SELECT COUNT(*) AS c FROM workers")["c"] == baseline_workers
        ), "worker rows not rolled back"
        assert (
            db.fetchone("SELECT COUNT(*) AS c FROM channels")["c"] == baseline_channels
        ), "channel row not rolled back"

        # And fire_worker was called for each successful hire (2 of them).
        fake_fire = fake_helpers["fire_worker"]
        assert fake_fire.call_count == 2, (
            f"fire_worker should be called once per successful hire; "
            f"got {fake_fire.call_count}"
        )

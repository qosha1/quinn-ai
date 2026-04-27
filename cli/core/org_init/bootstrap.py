"""Initial OKR + task seeding for new orgs.

Creates the bootstrap OKR (or whatever the wizard provided) in both the
beads store and the SQLite okrs table, and seeds the CEO with starter
tasks linked to the bootstrap OKR.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from .types import ObjectiveConfig

_logger = logging.getLogger(__name__)


def create_initial_okrs(
    org_path: Path,
    db,
    ceo_id: str,
    objectives: Optional[List[ObjectiveConfig]] = None,
) -> list[str]:
    """Create initial OKRs in the database.

    Priority order:
      1. Use objectives if provided directly (from CLI prompting / --okrs-file)
      2. Read from config/initial_okrs.json if it exists
      3. Create the bootstrap OKR as fallback

    Returns the list of OKR IDs created.
    """
    from cli.core.queries.okr import KeyResult, create_okr

    okr_ids: list[str] = []

    # Priority 1: directly provided objectives
    if objectives:
        for obj in objectives:
            key_results = [
                KeyResult(metric=kr.metric, target=kr.target, current=0.0, unit=kr.unit)
                for kr in obj.key_results
            ]
            okr = create_okr(
                db=db,
                title=obj.title,
                owner_id=ceo_id,
                description=None,
                status="active",
                key_results=key_results or None,
                due_date=None,
            )
            okr_ids.append(okr.id)
        return okr_ids

    # Priority 2: config file
    config_file = org_path / "config" / "initial_okrs.json"
    if config_file.exists():
        try:
            okrs_data = json.loads(config_file.read_text())
            for okr_config in okrs_data:
                key_results = [
                    KeyResult(
                        metric=kr_data["metric"],
                        target=kr_data["target"],
                        current=kr_data.get("current", 0.0),
                        unit=kr_data.get("unit", "count"),
                    )
                    for kr_data in okr_config.get("key_results", [])
                ]
                okr = create_okr(
                    db=db,
                    title=okr_config["title"],
                    owner_id=ceo_id,
                    description=okr_config.get("description"),
                    status="active",
                    key_results=key_results or None,
                    due_date=None,
                )
                okr_ids.append(okr.id)
            return okr_ids
        except (json.JSONDecodeError, KeyError) as e:
            _logger.warning(
                f"Failed to parse initial_okrs.json: {e}. Creating bootstrap OKR."
            )

    # Priority 3: bootstrap OKR
    okr_ids.append(_create_bootstrap_okr(org_path, db, ceo_id))
    return okr_ids


def _create_okr_bead(
    org_path: Path,
    title: str,
    description: str,
    ceo_id: str,
    priority: int = 1,
) -> Optional[str]:
    """Create an OKR as a bead via `bd create` and return its id.

    Returns None if bd is unavailable or the create failed; callers should
    fall back to SQLite-only storage. The returned id (e.g. 'myorg-abc123')
    is suitable as okr_id for create_okr() so both stores share an identifier
    (quinn-ai-lxp).
    """
    from cli.core.bd_wrapper import run_bd

    try:
        result = run_bd(
            args=[
                "create", title,
                "--type=epic",
                "--label=okr",
                f"--priority={priority}",
                f"--description={description}",
                f"--assignee={ceo_id}",
                "--json",
            ],
            org_path=org_path,
            worker_id=ceo_id,
            skip_permission_check=True,
            capture_output=True,
            # Bootstrap-OKR bead creation is best-effort; bd intermittently
            # hangs under concurrent test load (quinn-ai-5d4). Fast-fail back
            # to SQLite-only via the broad except below.
            timeout=10,
        )
        if result.returncode != 0:
            return None
        # bd may emit non-JSON warnings before the JSON object; find the
        # first '{' and parse from there.
        match = re.search(r"\{.*\}", result.stdout, re.DOTALL)
        if not match:
            return None
        return json.loads(match.group(0)).get("id")
    except Exception:
        _logger.exception("Failed to create OKR bead for '%s'", title)
        return None


def _create_bootstrap_okr(org_path: Path, db, ceo_id: str) -> str:
    """Create the default bootstrap OKR when no objectives were provided.

    Writes the OKR to BOTH stores with the same id:
      1. As a bead (via bd create) — source of truth for the dependency graph
      2. To SQLite okrs table — supplemental for KR progress aggregation

    If bead creation fails (bd unavailable, permission), the SQLite write
    still happens with a generated id so init doesn't fail; `qn org okr list`
    (which reads beads) will not surface the OKR in that case.
    """
    from cli.core.constants import (
        DEFAULT_BOOTSTRAP_OKR_DESCRIPTION,
        DEFAULT_BOOTSTRAP_OKR_TITLE,
    )
    from cli.core.queries.okr import KeyResult, create_okr

    key_results = [
        KeyResult(metric="team_size", target=3.0, current=1.0, unit="workers"),
        KeyResult(metric="processes_documented", target=3.0, current=0.0, unit="docs"),
    ]

    bead_id = _create_okr_bead(
        org_path=org_path,
        title=DEFAULT_BOOTSTRAP_OKR_TITLE,
        description=DEFAULT_BOOTSTRAP_OKR_DESCRIPTION,
        ceo_id=ceo_id,
    )

    okr = create_okr(
        db=db,
        title=DEFAULT_BOOTSTRAP_OKR_TITLE,
        owner_id=ceo_id,
        description=DEFAULT_BOOTSTRAP_OKR_DESCRIPTION,
        status="active",
        okr_id=bead_id,  # None → create_okr generates one
        key_results=key_results,
        due_date=None,
    )
    return okr.id


def create_initial_tasks(
    org_path: Path,
    db,
    ceo_id: str,
    okr_ids: list[str],
) -> None:
    """Seed the CEO with starter tasks linked to the bootstrap OKR.

    Fixes GAP 2 (CEO had OKRs but no actionable tasks). Failures here don't
    fail org init — the warning tells the operator to create tasks manually.
    """
    from cli.core.bd_wrapper import run_bd

    if not okr_ids:
        return

    okr_id = okr_ids[0]

    initial_tasks = [
        {
            "title": "Review org structure and onboarding materials",
            "description": "Read BRIEFING.md, STORAGE.md, CLAUDE.md to understand org structure and your responsibilities.",
            "priority": 1,
        },
        {
            "title": "Document initial org processes",
            "description": "Create documentation for how the org should operate (workflows, communication, decision-making).",
            "priority": 2,
        },
        {
            "title": "Plan initial team hiring",
            "description": "Identify which roles are needed first and create hiring plan to reach team_size target.",
            "priority": 2,
        },
    ]

    try:
        for task in initial_tasks:
            # NOTE: passing worker_id=ceo_id (not "system") so the
            # activity_signals FK to workers.id holds. There is no
            # "system" worker row.
            run_bd(
                args=[
                    "create",
                    task["title"],
                    "--type=task",
                    f"--priority={task['priority']}",
                    f"--description={task['description']}",
                    f"--assignee={ceo_id}",
                    f"--deps=serves:{okr_id}",
                ],
                org_path=org_path,
                worker_id=ceo_id,
                skip_permission_check=True,
                capture_output=True,
                timeout=15,  # quinn-ai-5d4: best-effort under concurrent load
            )
    except Exception as e:
        _logger.warning(f"Failed to create initial tasks: {e}")
        _logger.warning("CEO will need to create tasks manually from OKRs")

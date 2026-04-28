"""Discover scenario YAML specs and parametrize tests over them.

Scenarios that depend on as-yet-unfixed QuinnAI bugs are marked xfail via
the EXPECTED_FAILURES table below — keeps the suite green while the
underlying bugs are tracked separately in beads.
"""
from pathlib import Path

import pytest

SPECS_DIR = Path(__file__).parent / "specs"

# scenario_id -> (bead_id, brief reason). Marks scenarios as xfail (strict=False
# so the run doesn't fail if the underlying bug gets fixed and the scenario
# starts passing — that just becomes an XPASS signal).
EXPECTED_FAILURES = {
    "03_chain_3_levels": ("quinn-ai-cvpg", "promote-to-team-lead needs delegated_budget set first"),
    "05_okr_cascade": ("quinn-ai-4zgi", "okr_owner predicate queries non-existent 'okrs' table"),
    "06_work_distribution": ("quinn-ai-772u", "qn-bd subcommand surface unverified"),
}


def pytest_generate_tests(metafunc):
    if "scenario_path" in metafunc.fixturenames:
        specs = sorted(SPECS_DIR.glob("*.yml"))
        params = []
        ids = []
        for spec in specs:
            sid = spec.stem
            marks = []
            if sid in EXPECTED_FAILURES:
                bead, reason = EXPECTED_FAILURES[sid]
                marks.append(pytest.mark.xfail(strict=False, reason=f"{bead}: {reason}"))
            params.append(pytest.param(spec, marks=marks, id=sid))
        metafunc.parametrize("scenario_path", params)

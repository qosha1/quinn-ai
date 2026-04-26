"""
Tests for the worker onboarding helpers.
"""

from pathlib import Path

from cli.core.db import open_database, get_org_db_path
from cli.core.onboarding import (
    _load_worker_okrs,
    get_worker_env_vars,
    load_onboarding_context,
)
from cli.core.org_init import OrgInitConfig, init_org
from cli.core.queries import (
    create_okr,
    get_worker_by_name,
    KeyResult,
)


def _init_org(org_path: Path) -> None:
    """Initialize an organization for onboarding tests."""
    config = OrgInitConfig(path=org_path, name=org_path.name, ceo_name="CEO", ceo_role="CEO")
    result = init_org(config)
    assert result.success, result.error


def _create_sample_okr(db, owner_id: str) -> None:
    """Create a sample OKR with measurable key results."""
    create_okr(
        db=db,
        title="Onboarding visibility OKR",
        owner_id=owner_id,
        key_results=[
            KeyResult(metric="lighthouse", target=90.0, current=42.0, unit="score"),
            KeyResult(metric="coverage", target=80.0, current=50.0, unit="%"),
        ],
    )


def test_load_worker_okrs_returns_key_results(tmp_path: Path) -> None:
    org_path = tmp_path / "org"
    org_path.mkdir()

    _init_org(org_path)

    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None

        _create_sample_okr(db, ceo.id)

        okrs = _load_worker_okrs(db, ceo.id)
        assert len(okrs) == 1
        okr = okrs[0]
        assert "title" in okr and okr["title"] == "Onboarding visibility OKR"
        assert len(okr["key_results"]) == 2
        assert okr["key_results"][0]["metric"] == "lighthouse"
    finally:
        db.close()


def test_onboarding_environment_includes_worker_identity(tmp_path: Path) -> None:
    org_path = tmp_path / "org"
    org_path.mkdir()

    _init_org(org_path)

    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None

        _create_sample_okr(db, ceo.id)

        ctx = load_onboarding_context(db, ceo.id, org_path)
        env_vars = get_worker_env_vars(ctx, org_path, db)

        assert env_vars["WORKER_ID"] == ceo.id
        assert env_vars["QUINN_WORKER_ID"] == ceo.id
        assert "BRIEFING_PATH" in env_vars
        assert ctx.okrs, "Onboarding context should include OKRs"
    finally:
        db.close()

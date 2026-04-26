"""Tests for OKR creation during org initialization (GAP 1 fix)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from cli.core.org_init import create_initial_okrs, _create_bootstrap_okr
from cli.core.queries.okr import list_okrs, get_okrs_by_owner
from cli.core.db import init_database
from cli.core.constants import (
    DEFAULT_BOOTSTRAP_OKR_TITLE,
    DEFAULT_BOOTSTRAP_OKR_DESCRIPTION,
)


@pytest.fixture
def temp_org_dir():
    """Create a temporary org directory with config folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / "config").mkdir(parents=True)
        yield org_path


@pytest.fixture
def test_db():
    """Create a test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    db = init_database(db_path)
    yield db
    db.close()
    db_path.unlink()


def test_create_initial_okrs_from_config(temp_org_dir, test_db):
    """Test OKR creation from config/initial_okrs.json."""
    # Create config file with OKRs
    okrs_config = [
        {
            "title": "Launch product MVP",
            "description": "Build and launch minimum viable product",
            "key_results": [
                {"metric": "features_completed", "target": 5.0, "current": 0.0, "unit": "features"},
                {"metric": "test_coverage", "target": 80.0, "current": 0.0, "unit": "%"},
            ],
        },
        {
            "title": "Hire engineering team",
            "key_results": [
                {"metric": "engineers_hired", "target": 3.0, "current": 0.0, "unit": "workers"},
            ],
        },
    ]

    config_file = temp_org_dir / "config" / "initial_okrs.json"
    config_file.write_text(json.dumps(okrs_config, indent=2))

    # Create CEO worker
    from cli.core.org import Org
    org = Org(test_db)
    ceo = org.init("Alice", "CEO")

    # Create OKRs
    create_initial_okrs(temp_org_dir, test_db, ceo.id)

    # Verify OKRs were created in database
    okrs = get_okrs_by_owner(test_db, ceo.id)
    assert len(okrs) == 2

    # Check first OKR
    okr1 = next(o for o in okrs if o.title == "Launch product MVP")
    assert okr1.description == "Build and launch minimum viable product"
    assert okr1.owner_worker_id == ceo.id
    assert okr1.status == "active"
    assert len(okr1.key_results) == 2
    assert okr1.key_results[0].metric == "features_completed"
    assert okr1.key_results[0].target == 5.0
    assert okr1.key_results[0].current == 0.0
    assert okr1.key_results[0].unit == "features"

    # Check second OKR
    okr2 = next(o for o in okrs if o.title == "Hire engineering team")
    assert len(okr2.key_results) == 1
    assert okr2.key_results[0].metric == "engineers_hired"


def test_create_bootstrap_okr_no_config(temp_org_dir, test_db):
    """Test bootstrap OKR creation when no config file exists."""
    # Create CEO worker
    from cli.core.org import Org
    org = Org(test_db)
    ceo = org.init("Bob", "CEO")

    # Create OKRs (no config file exists)
    create_initial_okrs(temp_org_dir, test_db, ceo.id)

    # Verify bootstrap OKR was created
    okrs = get_okrs_by_owner(test_db, ceo.id)
    assert len(okrs) == 1

    bootstrap_okr = okrs[0]
    assert bootstrap_okr.title == DEFAULT_BOOTSTRAP_OKR_TITLE
    assert bootstrap_okr.description == DEFAULT_BOOTSTRAP_OKR_DESCRIPTION
    assert bootstrap_okr.owner_worker_id == ceo.id
    assert bootstrap_okr.status == "active"

    # Check bootstrap key results
    assert len(bootstrap_okr.key_results) >= 2
    metrics = {kr.metric for kr in bootstrap_okr.key_results}
    assert "team_size" in metrics
    assert "processes_documented" in metrics


def test_create_initial_okrs_malformed_config(temp_org_dir, test_db):
    """Test fallback to bootstrap when config is malformed."""
    # Create malformed config file
    config_file = temp_org_dir / "config" / "initial_okrs.json"
    config_file.write_text("{ this is not valid json }")

    # Create CEO worker
    from cli.core.org import Org
    org = Org(test_db)
    ceo = org.init("Charlie", "CEO")

    # Create OKRs (should fall back to bootstrap)
    create_initial_okrs(temp_org_dir, test_db, ceo.id)

    # Verify bootstrap OKR was created
    okrs = get_okrs_by_owner(test_db, ceo.id)
    assert len(okrs) == 1
    assert okrs[0].title == DEFAULT_BOOTSTRAP_OKR_TITLE


def test_create_bootstrap_okr_directly(test_db):
    """Test _create_bootstrap_okr function directly."""
    # Create CEO worker
    from cli.core.org import Org
    org = Org(test_db)
    ceo = org.init("Diana", "CEO")

    # Create bootstrap OKR
    _create_bootstrap_okr(test_db, ceo.id)

    # Verify OKR was created
    okrs = get_okrs_by_owner(test_db, ceo.id)
    assert len(okrs) == 1

    okr = okrs[0]
    assert okr.title == DEFAULT_BOOTSTRAP_OKR_TITLE
    assert okr.description == DEFAULT_BOOTSTRAP_OKR_DESCRIPTION
    assert okr.owner_worker_id == ceo.id
    assert okr.status == "active"
    assert len(okr.key_results) >= 2


def test_okr_key_results_have_valid_structure(temp_org_dir, test_db):
    """Test that key results have correct structure."""
    # Create config with key results
    okrs_config = [
        {
            "title": "Test objective",
            "key_results": [
                {"metric": "metric_1", "target": 100.0, "unit": "%"},
                {"metric": "metric_2", "target": 50.0, "current": 10.0, "unit": "count"},
            ],
        },
    ]

    config_file = temp_org_dir / "config" / "initial_okrs.json"
    config_file.write_text(json.dumps(okrs_config, indent=2))

    # Create CEO worker
    from cli.core.org import Org
    org = Org(test_db)
    ceo = org.init("Eve", "CEO")

    # Create OKRs
    create_initial_okrs(temp_org_dir, test_db, ceo.id)

    # Verify key results structure
    okrs = get_okrs_by_owner(test_db, ceo.id)
    okr = okrs[0]

    kr1 = okr.key_results[0]
    assert kr1.metric == "metric_1"
    assert kr1.target == 100.0
    assert kr1.current == 0.0  # Should default to 0.0
    assert kr1.unit == "%"

    kr2 = okr.key_results[1]
    assert kr2.metric == "metric_2"
    assert kr2.target == 50.0
    assert kr2.current == 10.0  # Explicit current value
    assert kr2.unit == "count"


def test_multiple_okrs_from_config(temp_org_dir, test_db):
    """Test creating multiple OKRs from config."""
    # Create config with multiple OKRs
    okrs_config = [
        {"title": "OKR 1", "key_results": []},
        {"title": "OKR 2", "key_results": []},
        {"title": "OKR 3", "key_results": []},
    ]

    config_file = temp_org_dir / "config" / "initial_okrs.json"
    config_file.write_text(json.dumps(okrs_config, indent=2))

    # Create CEO worker
    from cli.core.org import Org
    org = Org(test_db)
    ceo = org.init("Frank", "CEO")

    # Create OKRs
    create_initial_okrs(temp_org_dir, test_db, ceo.id)

    # Verify all OKRs were created
    okrs = get_okrs_by_owner(test_db, ceo.id)
    assert len(okrs) == 3
    titles = {o.title for o in okrs}
    assert titles == {"OKR 1", "OKR 2", "OKR 3"}


def test_okr_without_key_results(temp_org_dir, test_db):
    """Test creating OKR without key results."""
    # Create config with OKR but no key results
    okrs_config = [
        {
            "title": "High-level objective",
            "description": "This OKR has no key results yet",
        },
    ]

    config_file = temp_org_dir / "config" / "initial_okrs.json"
    config_file.write_text(json.dumps(okrs_config, indent=2))

    # Create CEO worker
    from cli.core.org import Org
    org = Org(test_db)
    ceo = org.init("Grace", "CEO")

    # Create OKRs
    create_initial_okrs(temp_org_dir, test_db, ceo.id)

    # Verify OKR was created without key results
    okrs = get_okrs_by_owner(test_db, ceo.id)
    assert len(okrs) == 1
    assert okrs[0].title == "High-level objective"
    assert okrs[0].description == "This OKR has no key results yet"
    assert len(okrs[0].key_results) == 0

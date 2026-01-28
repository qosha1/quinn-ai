"""
Tests for automatic onboarding file generation.

Verifies that BRIEFING.md, STORAGE.md, and WELCOME.md are created
when a worker transitions to the onboarding lifecycle state.
"""

from pathlib import Path

from cli.core.db import open_database, get_org_db_path
from cli.core.org_init import OrgInitConfig, init_org
from cli.core.queries import get_worker_by_name
from cli.core.worker import Worker
from cli.core.storage import StorageManager


def test_onboarding_creates_all_files(tmp_path: Path) -> None:
    """Test that start_onboarding() creates BRIEFING.md, STORAGE.md, WELCOME.md."""
    org_path = tmp_path / "org"
    org_path.mkdir()

    # Initialize org
    config = OrgInitConfig(
        path=org_path,
        name=org_path.name,
        ceo_name="CEO",
        ceo_role="CEO",
    )
    result = init_org(config)
    assert result.success, result.error

    db = open_database(get_org_db_path(org_path))

    try:
        # Get CEO
        ceo_data = get_worker_by_name(db, "ceo")
        assert ceo_data is not None
        ceo = Worker.get(db, ceo_data.id)
        ceo._org_path = org_path

        # Hire a worker (creates in 'pending' state)
        new_worker = ceo.hire(
            name="Alice",
            role="Engineer",
            skills={"coding": 80},
            cost=50,
        )
        new_worker._org_path = org_path

        # Verify worker starts in pending state
        assert new_worker.lifecycle_status == "pending"

        # Get storage path for the new worker
        storage = StorageManager(org_path, db)
        worker_dir = storage.get_worker_path(new_worker.id)

        # Verify files don't exist yet
        assert not (worker_dir / "BRIEFING.md").exists()
        assert not (worker_dir / "STORAGE.md").exists()
        assert not (worker_dir / "WELCOME.md").exists()

        # Transition to onboarding - should create files
        new_worker.start_onboarding()

        # Verify files now exist
        assert (worker_dir / "BRIEFING.md").exists()
        assert (worker_dir / "STORAGE.md").exists()
        assert (worker_dir / "WELCOME.md").exists()

        # Verify BRIEFING.md content includes worker info
        briefing_content = (worker_dir / "BRIEFING.md").read_text()
        assert "Alice" in briefing_content
        assert "Engineer" in briefing_content

        # Verify STORAGE.md exists and has content
        storage_content = (worker_dir / "STORAGE.md").read_text()
        assert "Storage Architecture Guide" in storage_content or "Your Storage Path" in storage_content

        # Verify WELCOME.md exists and has content
        welcome_content = (worker_dir / "WELCOME.md").read_text()
        assert "QuinnAI Worker Session" in welcome_content or "Ready to begin" in welcome_content

    finally:
        db.close()


def test_onboarding_creates_onboarding_directory(tmp_path: Path) -> None:
    """Test that onboarding creates .onboarding directory with marker."""
    org_path = tmp_path / "org"
    org_path.mkdir()

    # Initialize org
    config = OrgInitConfig(
        path=org_path,
        name=org_path.name,
        ceo_name="CEO",
        ceo_role="CEO",
    )
    result = init_org(config)
    assert result.success, result.error

    db = open_database(get_org_db_path(org_path))

    try:
        # Get CEO
        ceo_data = get_worker_by_name(db, "ceo")
        assert ceo_data is not None
        ceo = Worker.get(db, ceo_data.id)
        ceo._org_path = org_path

        # Hire a worker
        new_worker = ceo.hire(
            name="Bob",
            role="Designer",
            skills={"design": 90},
            cost=60,
        )
        new_worker._org_path = org_path

        # Transition to onboarding
        new_worker.start_onboarding()

        # Verify .onboarding directory exists with marker
        storage = StorageManager(org_path, db)
        worker_dir = storage.get_worker_path(new_worker.id)
        onboarding_dir = worker_dir / ".onboarding"

        assert onboarding_dir.exists()
        assert onboarding_dir.is_dir()
        assert (onboarding_dir / "initialized").exists()

    finally:
        db.close()


def test_onboarding_idempotent(tmp_path: Path) -> None:
    """Test that calling start_onboarding() multiple times doesn't break."""
    org_path = tmp_path / "org"
    org_path.mkdir()

    # Initialize org
    config = OrgInitConfig(
        path=org_path,
        name=org_path.name,
        ceo_name="CEO",
        ceo_role="CEO",
    )
    result = init_org(config)
    assert result.success, result.error

    db = open_database(get_org_db_path(org_path))

    try:
        # Get CEO
        ceo_data = get_worker_by_name(db, "ceo")
        assert ceo_data is not None
        ceo = Worker.get(db, ceo_data.id)
        ceo._org_path = org_path

        # Hire a worker
        new_worker = ceo.hire(
            name="Carol",
            role="QA",
            skills={"testing": 85},
            cost=45,
        )
        new_worker._org_path = org_path

        # Get storage path
        storage = StorageManager(org_path, db)
        worker_dir = storage.get_worker_path(new_worker.id)

        # First onboarding
        new_worker.start_onboarding()
        assert (worker_dir / "BRIEFING.md").exists()

        # Read original content
        original_briefing = (worker_dir / "BRIEFING.md").read_text()

        # Second call to prepare_worker_onboarding should be idempotent
        from cli.core.onboarding import prepare_worker_onboarding
        prepare_worker_onboarding(db, new_worker.id, org_path)

        # Files should still exist and content should be similar (may have updated timestamp)
        assert (worker_dir / "BRIEFING.md").exists()
        assert (worker_dir / "STORAGE.md").exists()
        assert (worker_dir / "WELCOME.md").exists()

        new_briefing = (worker_dir / "BRIEFING.md").read_text()
        # Worker name should still be present
        assert "Carol" in new_briefing
        assert "QA" in new_briefing

    finally:
        db.close()


def test_onboarding_hierarchical_storage(tmp_path: Path) -> None:
    """Test that onboarding creates files in hierarchical storage path."""
    org_path = tmp_path / "org"
    org_path.mkdir()

    # Initialize org
    config = OrgInitConfig(
        path=org_path,
        name=org_path.name,
        ceo_name="CEO",
        ceo_role="CEO",
    )
    result = init_org(config)
    assert result.success, result.error

    db = open_database(get_org_db_path(org_path))

    try:
        # Get CEO
        ceo_data = get_worker_by_name(db, "ceo")
        assert ceo_data is not None
        ceo = Worker.get(db, ceo_data.id)
        ceo._org_path = org_path

        # Hire two workers under CEO
        engineer1 = ceo.hire(
            name="Engineer1",
            role="Engineer",
            skills={"coding": 80},
            cost=50,
        )
        engineer1._org_path = org_path
        engineer1.start_onboarding()

        engineer2 = ceo.hire(
            name="Engineer2",
            role="Engineer",
            skills={"coding": 85},
            cost=55,
        )
        engineer2._org_path = org_path
        engineer2.start_onboarding()

        # Verify hierarchical paths
        storage = StorageManager(org_path, db)

        # CEO path: storage/workers/{ceo-id}/
        ceo_dir = storage.get_worker_path(ceo.id)
        assert ceo.id in str(ceo_dir)
        assert "storage/workers" in str(ceo_dir)

        # Engineer1 path: storage/workers/{ceo-id}/{engineer1-id}/
        engineer1_dir = storage.get_worker_path(engineer1.id)
        # Engineer's path should contain CEO's path as parent
        assert str(ceo_dir) in str(engineer1_dir)
        assert engineer1.id in str(engineer1_dir)

        # Engineer2 path: storage/workers/{ceo-id}/{engineer2-id}/
        engineer2_dir = storage.get_worker_path(engineer2.id)
        # Engineer's path should contain CEO's path as parent
        assert str(ceo_dir) in str(engineer2_dir)
        assert engineer2.id in str(engineer2_dir)

        # Verify all have onboarding files
        assert (engineer1_dir / "BRIEFING.md").exists()
        assert (engineer1_dir / "STORAGE.md").exists()
        assert (engineer1_dir / "WELCOME.md").exists()

        assert (engineer2_dir / "BRIEFING.md").exists()
        assert (engineer2_dir / "STORAGE.md").exists()
        assert (engineer2_dir / "WELCOME.md").exists()

        # Verify engineer's BRIEFING references CEO as manager
        engineer1_briefing = (engineer1_dir / "BRIEFING.md").read_text()
        assert "CEO" in engineer1_briefing

    finally:
        db.close()

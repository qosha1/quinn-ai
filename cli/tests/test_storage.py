"""
Unit tests for storage abstraction.
"""

import tempfile
from pathlib import Path

import pytest

from cli.core.db import init_database
from cli.core.queries import create_team, create_worker
from cli.core.storage import (
    StorageManager,
    StorageError,
    WorkerStorageNotFound,
    StorageAlreadyFrozen,
    STORAGE_DIR,
    SHARED_DIR,
    WORKERS_DIR,
    FROZEN_SUFFIX,
    DEFAULT_SHARED_TOPICS,
)


@pytest.fixture
def org_path():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage_manager(org_path):
    """Create a storage manager without database."""
    return StorageManager(org_path)


@pytest.fixture
def db(org_path):
    """Create and initialize a test database."""
    db_path = org_path / "live" / "quinn.db"
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def storage_with_db(org_path, db):
    """Create a storage manager with database."""
    return StorageManager(org_path, db=db)


@pytest.fixture
def org_hierarchy(db):
    """Create a test org hierarchy.

    Creates:
    - CEO (root, no manager)
    - Director (reports to CEO)
    - Engineer (reports to Director)
    """
    team = create_team(db, "Engineering")

    ceo = create_worker(
        db, name="CEO", role="ceo", team_id=team.id, cost=100, worker_id="ceo"
    )

    director = create_worker(
        db, name="Director", role="director", team_id=team.id, cost=80,
        manager_id=ceo.id, worker_id="director-abc"
    )

    engineer = create_worker(
        db, name="Engineer", role="engineer", team_id=team.id, cost=50,
        manager_id=director.id, worker_id="engineer-xyz"
    )

    return {"ceo": ceo, "director": director, "engineer": engineer, "team": team}


class TestStorageManagerInit:
    """Test StorageManager initialization."""

    def test_init_sets_paths(self, org_path):
        """Should set org_path and storage_root correctly."""
        sm = StorageManager(org_path)
        assert sm.org_path == org_path
        assert sm.storage_root == org_path / STORAGE_DIR

    def test_init_with_db(self, org_path, db):
        """Should accept optional database."""
        sm = StorageManager(org_path, db=db)
        assert sm.db is db


class TestSharedStorage:
    """Test shared storage operations."""

    def test_get_shared_path(self, storage_manager, org_path):
        """Should return correct shared path for topic."""
        path = storage_manager.get_shared_path("engineering")
        assert path == org_path / STORAGE_DIR / SHARED_DIR / "engineering"

    def test_ensure_shared_storage_creates_dir(self, storage_manager):
        """Should create shared directory if not exists."""
        path = storage_manager.ensure_shared_storage("engineering")
        assert path.exists()
        assert path.is_dir()

    def test_ensure_shared_storage_idempotent(self, storage_manager):
        """Should not fail if directory already exists."""
        path1 = storage_manager.ensure_shared_storage("engineering")
        path2 = storage_manager.ensure_shared_storage("engineering")
        assert path1 == path2
        assert path1.exists()


class TestInitializeStorage:
    """Test storage initialization."""

    def test_initialize_creates_default_topics(self, storage_manager, org_path):
        """Should create default shared topic directories."""
        storage_manager.initialize_storage()

        for topic in DEFAULT_SHARED_TOPICS:
            path = org_path / STORAGE_DIR / SHARED_DIR / topic
            assert path.exists(), f"Missing topic: {topic}"

    def test_initialize_creates_workers_dir(self, storage_manager, org_path):
        """Should create workers root directory."""
        storage_manager.initialize_storage()
        workers_root = org_path / STORAGE_DIR / WORKERS_DIR
        assert workers_root.exists()


class TestWorkerPathWithoutDb:
    """Test worker path operations without database (direct reports_to)."""

    def test_get_worker_path_root(self, storage_manager, org_path):
        """CEO path should be directly under workers."""
        path = storage_manager.get_worker_path("ceo", reports_to="")
        assert path == org_path / STORAGE_DIR / WORKERS_DIR / "ceo"

    def test_get_worker_path_nested(self, storage_manager, org_path):
        """Nested worker path should mirror hierarchy.

        Without a database, reports_to assumes parent is at root level.
        """
        # Director under CEO (CEO at root)
        path = storage_manager.get_worker_path("director-abc", reports_to="ceo")
        ceo_path = org_path / STORAGE_DIR / WORKERS_DIR / "ceo"
        assert path == ceo_path / "director-abc"

    def test_get_worker_path_one_level_deep(self, storage_manager, org_path):
        """Test creating path one level deep from root.

        Without a database, we can only reliably create paths where
        reports_to is at root (reports_to="") or one level deep
        (reports_to points to a root worker).
        """
        # Create CEO at root
        ceo_path = storage_manager.ensure_worker_storage("ceo", reports_to="")
        # Create director under CEO
        dir_path = storage_manager.ensure_worker_storage("director-abc", reports_to="ceo")

        expected_ceo = org_path / STORAGE_DIR / WORKERS_DIR / "ceo"
        expected_dir = expected_ceo / "director-abc"

        assert ceo_path == expected_ceo
        assert dir_path == expected_dir
        assert ceo_path.exists()
        assert dir_path.exists()

    def test_get_worker_path_without_db_or_reports_to_fails(self, storage_manager):
        """Should raise if no db and no reports_to provided."""
        with pytest.raises(ValueError, match="Database required"):
            storage_manager.get_worker_path("some-worker")


class TestWorkerPathWithDb:
    """Test worker path operations with database lookup."""

    def test_get_worker_path_ceo_from_db(self, storage_with_db, org_hierarchy, org_path):
        """CEO path should be under workers root."""
        path = storage_with_db.get_worker_path("ceo")
        assert path == org_path / STORAGE_DIR / WORKERS_DIR / "ceo"

    def test_get_worker_path_director_from_db(self, storage_with_db, org_hierarchy, org_path):
        """Director path should be under CEO."""
        path = storage_with_db.get_worker_path("director-abc")
        expected = org_path / STORAGE_DIR / WORKERS_DIR / "ceo" / "director-abc"
        assert path == expected

    def test_get_worker_path_engineer_from_db(self, storage_with_db, org_hierarchy, org_path):
        """Engineer path should be under Director under CEO."""
        path = storage_with_db.get_worker_path("engineer-xyz")
        expected = org_path / STORAGE_DIR / WORKERS_DIR / "ceo" / "director-abc" / "engineer-xyz"
        assert path == expected

    def test_get_worker_path_not_found(self, storage_with_db):
        """Should raise if worker not in database."""
        with pytest.raises(WorkerStorageNotFound):
            storage_with_db.get_worker_path("nonexistent-worker")


class TestEnsureWorkerStorage:
    """Test worker storage creation."""

    def test_ensure_worker_storage_creates_dir(self, storage_manager):
        """Should create worker directory."""
        path = storage_manager.ensure_worker_storage("test-worker", reports_to="")
        assert path.exists()
        assert path.is_dir()

    def test_ensure_worker_storage_creates_hierarchy_with_db(self, storage_with_db, org_hierarchy, org_path):
        """Should create full hierarchy path when using database.

        Full hierarchy (3+ levels) requires database for lookup.
        """
        # Using database-backed storage manager with hierarchy
        storage_with_db.ensure_worker_storage("ceo")
        storage_with_db.ensure_worker_storage("director-abc")
        path = storage_with_db.ensure_worker_storage("engineer-xyz")

        expected = org_path / STORAGE_DIR / WORKERS_DIR / "ceo" / "director-abc" / "engineer-xyz"
        assert path == expected
        assert path.exists()

    def test_ensure_worker_storage_idempotent(self, storage_manager):
        """Should not fail if directory exists."""
        path1 = storage_manager.ensure_worker_storage("worker", reports_to="")
        path2 = storage_manager.ensure_worker_storage("worker", reports_to="")
        assert path1 == path2


class TestWorkerStorageExists:
    """Test worker storage existence checks."""

    def test_worker_storage_exists_true(self, storage_manager):
        """Should return True if storage exists."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        assert storage_manager.worker_storage_exists("worker", reports_to="")

    def test_worker_storage_exists_false(self, storage_manager):
        """Should return False if storage doesn't exist."""
        assert not storage_manager.worker_storage_exists("nonexistent", reports_to="")


class TestFreezeWorker:
    """Test worker storage freezing."""

    def test_freeze_worker_renames_dir(self, storage_manager):
        """Should rename directory with .frozen suffix."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        frozen_path = storage_manager.freeze_worker("worker", reports_to="")

        assert frozen_path.name == f"worker{FROZEN_SUFFIX}"
        assert frozen_path.exists()
        # Original should not exist
        original_path = storage_manager.get_worker_path("worker", reports_to="")
        assert not original_path.exists()

    def test_freeze_worker_not_found(self, storage_manager):
        """Should raise if worker storage doesn't exist."""
        with pytest.raises(WorkerStorageNotFound):
            storage_manager.freeze_worker("nonexistent", reports_to="")

    def test_freeze_worker_already_frozen(self, storage_manager):
        """Should raise if already frozen."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        storage_manager.freeze_worker("worker", reports_to="")

        with pytest.raises(StorageAlreadyFrozen):
            storage_manager.freeze_worker("worker", reports_to="")


class TestIsWorkerFrozen:
    """Test frozen state checks."""

    def test_is_worker_frozen_false(self, storage_manager):
        """Should return False if not frozen."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        assert not storage_manager.is_worker_frozen("worker", reports_to="")

    def test_is_worker_frozen_true(self, storage_manager):
        """Should return True if frozen."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        storage_manager.freeze_worker("worker", reports_to="")
        assert storage_manager.is_worker_frozen("worker", reports_to="")


class TestUnfreezeWorker:
    """Test worker storage unfreezing."""

    def test_unfreeze_worker_restores_dir(self, storage_manager):
        """Should restore directory without .frozen suffix."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        storage_manager.freeze_worker("worker", reports_to="")
        restored_path = storage_manager.unfreeze_worker("worker", reports_to="")

        assert restored_path.name == "worker"
        assert restored_path.exists()

    def test_unfreeze_worker_not_frozen(self, storage_manager):
        """Should raise if not frozen."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        with pytest.raises(WorkerStorageNotFound):
            storage_manager.unfreeze_worker("worker", reports_to="")


class TestCleanupWorker:
    """Test worker cleanup operations."""

    def test_cleanup_worker_deletes_dir(self, storage_manager):
        """Should delete worker directory."""
        path = storage_manager.ensure_worker_storage("worker", reports_to="")
        storage_manager.cleanup_worker("worker", reports_to="")
        assert not path.exists()

    def test_cleanup_worker_moves_useful_files(self, storage_manager, org_path):
        """Should move specified files to shared storage."""
        # Create worker storage with a file
        path = storage_manager.ensure_worker_storage("worker", reports_to="")
        test_file = path / "important.txt"
        test_file.write_text("important content")

        # Cleanup with useful files
        storage_manager.cleanup_worker(
            "worker",
            useful_files=[Path("important.txt")],
            target_topic="company",
            reports_to=""
        )

        # Check file was moved to shared
        shared_path = org_path / STORAGE_DIR / SHARED_DIR / "company" / "from-worker"
        moved_file = shared_path / "important.txt"
        assert moved_file.exists()
        assert moved_file.read_text() == "important content"

        # Original dir should be deleted
        assert not path.exists()

    def test_cleanup_worker_handles_frozen(self, storage_manager):
        """Should cleanup frozen storage."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        storage_manager.freeze_worker("worker", reports_to="")

        # Should work on frozen dir
        storage_manager.cleanup_worker("worker", reports_to="")

        # Both paths should not exist
        path = storage_manager.get_worker_path("worker", reports_to="")
        frozen_path = path.parent / f"worker{FROZEN_SUFFIX}"
        assert not path.exists()
        assert not frozen_path.exists()

    def test_cleanup_worker_not_found(self, storage_manager):
        """Should raise if storage doesn't exist."""
        with pytest.raises(WorkerStorageNotFound):
            storage_manager.cleanup_worker("nonexistent", reports_to="")

    def test_cleanup_handles_file_name_conflicts(self, storage_manager):
        """Should handle duplicate file names."""
        path = storage_manager.ensure_worker_storage("worker", reports_to="")

        # Create file
        test_file = path / "doc.txt"
        test_file.write_text("content 1")

        # Pre-create a file in shared with same name
        shared_dir = storage_manager.ensure_shared_storage("company")
        archive_dir = shared_dir / "from-worker"
        archive_dir.mkdir()
        existing_file = archive_dir / "doc.txt"
        existing_file.write_text("existing")

        # Cleanup should rename the new file
        storage_manager.cleanup_worker(
            "worker",
            useful_files=[Path("doc.txt")],
            target_topic="company",
            reports_to=""
        )

        # Both files should exist
        assert existing_file.exists()
        renamed_file = archive_dir / "doc_1.txt"
        assert renamed_file.exists()
        assert renamed_file.read_text() == "content 1"


class TestListWorkerFiles:
    """Test listing worker files."""

    def test_list_worker_files_empty(self, storage_manager):
        """Should return empty list for empty storage."""
        storage_manager.ensure_worker_storage("worker", reports_to="")
        files = storage_manager.list_worker_files("worker", reports_to="")
        assert files == []

    def test_list_worker_files_with_files(self, storage_manager):
        """Should list all files in storage."""
        path = storage_manager.ensure_worker_storage("worker", reports_to="")

        # Create some files
        (path / "file1.txt").write_text("content")
        (path / "file2.py").write_text("code")
        subdir = path / "subdir"
        subdir.mkdir()
        (subdir / "nested.md").write_text("docs")

        files = storage_manager.list_worker_files("worker", reports_to="")

        assert len(files) == 3
        assert Path("file1.txt") in files
        assert Path("file2.py") in files
        assert Path("subdir/nested.md") in files

    def test_list_worker_files_frozen(self, storage_manager):
        """Should list files in frozen storage."""
        path = storage_manager.ensure_worker_storage("worker", reports_to="")
        (path / "file.txt").write_text("content")
        storage_manager.freeze_worker("worker", reports_to="")

        files = storage_manager.list_worker_files("worker", reports_to="")
        assert len(files) == 1
        assert Path("file.txt") in files

    def test_list_worker_files_not_found(self, storage_manager):
        """Should raise if storage doesn't exist."""
        with pytest.raises(WorkerStorageNotFound):
            storage_manager.list_worker_files("nonexistent", reports_to="")


class TestGetStorageStats:
    """Test storage statistics."""

    def test_get_storage_stats_empty(self, storage_manager):
        """Should return zeros for empty storage."""
        stats = storage_manager.get_storage_stats()
        assert stats["total_workers"] == 0
        assert stats["frozen_workers"] == 0
        assert stats["shared_topics"] == []
        assert stats["total_size_bytes"] == 0

    def test_get_storage_stats_with_data(self, storage_manager):
        """Should count workers and shared topics."""
        # Initialize storage
        storage_manager.initialize_storage()

        # Create some workers
        path1 = storage_manager.ensure_worker_storage("worker1", reports_to="")
        (path1 / "file.txt").write_text("test content")
        storage_manager.ensure_worker_storage("worker2", reports_to="")

        # Freeze one
        storage_manager.ensure_worker_storage("worker3", reports_to="")
        storage_manager.freeze_worker("worker3", reports_to="")

        stats = storage_manager.get_storage_stats()

        # Workers count includes nested dirs, but we created root workers only
        assert stats["total_workers"] >= 2
        assert stats["frozen_workers"] >= 1
        assert set(DEFAULT_SHARED_TOPICS).issubset(set(stats["shared_topics"]))
        assert stats["total_size_bytes"] > 0


class TestHierarchyChain:
    """Test hierarchy chain building."""

    def test_hierarchy_chain_ceo(self, storage_with_db, org_hierarchy):
        """CEO chain should be just CEO."""
        chain = storage_with_db._get_worker_hierarchy_chain("ceo")
        assert chain == ["ceo"]

    def test_hierarchy_chain_director(self, storage_with_db, org_hierarchy):
        """Director chain should be CEO -> Director."""
        chain = storage_with_db._get_worker_hierarchy_chain("director-abc")
        assert chain == ["ceo", "director-abc"]

    def test_hierarchy_chain_engineer(self, storage_with_db, org_hierarchy):
        """Engineer chain should be CEO -> Director -> Engineer."""
        chain = storage_with_db._get_worker_hierarchy_chain("engineer-xyz")
        assert chain == ["ceo", "director-abc", "engineer-xyz"]

    def test_hierarchy_chain_worker_not_found(self, storage_with_db):
        """Should raise for nonexistent worker."""
        with pytest.raises(WorkerStorageNotFound):
            storage_with_db._get_worker_hierarchy_chain("nonexistent")

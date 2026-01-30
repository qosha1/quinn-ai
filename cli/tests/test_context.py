"""
Unit tests for OrgContext dependency injection container.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.context import (
    OrgContext,
    OrgContextError,
    OrgNotFoundError,
)
from core.db import init_database, get_org_db_path
from core.config import OrgConfig, ProvidersConfig, WorkerTemplatesConfig


@pytest.fixture
def temp_org_path():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def org_with_config(temp_org_path):
    """Create an org with config files and initialized database."""
    # Create config directory
    config_dir = temp_org_path / "config"
    config_dir.mkdir(parents=True)

    # Create minimal providers.yaml
    providers_yaml = config_dir / "providers.yaml"
    providers_yaml.write_text("""\
default: anthropic
providers:
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
thresholds:
  coding: 80
  reasoning: 60
  research: 80
""")

    # Initialize database
    db_path = get_org_db_path(temp_org_path)
    db = init_database(db_path)
    db.close()

    return temp_org_path


class TestOrgContextCreate:
    """Test OrgContext.create() factory method."""

    def test_create_from_valid_org(self, org_with_config):
        """Should create context from valid initialized org."""
        ctx = OrgContext.create(org_with_config)
        try:
            # Use resolve() to handle macOS /var vs /private/var symlink
            assert ctx.org_path.resolve() == org_with_config.resolve()
            assert ctx.db is not None
            assert ctx.config is not None
            assert ctx.config.providers.default == "anthropic"
        finally:
            ctx.close()

    def test_create_nonexistent_path(self, temp_org_path):
        """Should raise OrgNotFoundError for nonexistent path."""
        nonexistent = temp_org_path / "does-not-exist"
        with pytest.raises(OrgNotFoundError) as exc_info:
            OrgContext.create(nonexistent)
        assert str(nonexistent) in str(exc_info.value)

    def test_create_uninitialized_org(self, temp_org_path):
        """Should raise OrgNotFoundError for org without database."""
        # Create config but not database
        config_dir = temp_org_path / "config"
        config_dir.mkdir(parents=True)
        providers_yaml = config_dir / "providers.yaml"
        providers_yaml.write_text("default: anthropic\nproviders:\n  anthropic:\n    enabled: true\n    api_key: test")

        with pytest.raises(OrgNotFoundError):
            OrgContext.create(temp_org_path)

    def test_create_missing_config(self, temp_org_path):
        """Should raise FileNotFoundError for missing config."""
        # Create database but not config
        db_path = get_org_db_path(temp_org_path)
        db = init_database(db_path)
        db.close()

        with pytest.raises(FileNotFoundError):
            OrgContext.create(temp_org_path)


class TestOrgContextCreateNew:
    """Test OrgContext.create_new() factory method."""

    def test_create_new_org(self, temp_org_path):
        """Should create new org with database and config."""
        ctx = OrgContext.create_new(temp_org_path, create_config=True)
        try:
            # Use resolve() to handle macOS /var vs /private/var symlink
            assert ctx.org_path.resolve() == temp_org_path.resolve()
            assert ctx.db is not None
            assert ctx.config is not None

            # Verify database was created
            db_path = get_org_db_path(temp_org_path)
            assert db_path.exists()

            # Verify config was created
            config_path = temp_org_path / "config" / "providers.yaml"
            assert config_path.exists()
        finally:
            ctx.close()

    def test_create_new_without_config_creation(self, temp_org_path):
        """Should fail if config missing and create_config=False."""
        with pytest.raises(FileNotFoundError):
            OrgContext.create_new(temp_org_path, create_config=False)

    def test_create_new_existing_config(self, temp_org_path):
        """Should use existing config if present."""
        # Create custom config
        config_dir = temp_org_path / "config"
        config_dir.mkdir(parents=True)
        providers_yaml = config_dir / "providers.yaml"
        providers_yaml.write_text("""\
default: openai
providers:
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
""")

        ctx = OrgContext.create_new(temp_org_path, create_config=True)
        try:
            # Should use existing config, not overwrite
            assert ctx.config.providers.default == "openai"
        finally:
            ctx.close()


class TestOrgContextProperties:
    """Test OrgContext properties and metadata."""

    def test_org_name(self, org_with_config):
        """Should return org folder name."""
        with OrgContext.create(org_with_config) as ctx:
            assert ctx.org_name == org_with_config.name

    def test_db_path(self, org_with_config):
        """Should return database file path."""
        with OrgContext.create(org_with_config) as ctx:
            expected = get_org_db_path(org_with_config)
            # Use resolve() to handle macOS /var vs /private/var symlink
            assert ctx.db_path.resolve() == expected.resolve()

    def test_config_path(self, org_with_config):
        """Should return config directory path."""
        with OrgContext.create(org_with_config) as ctx:
            expected = org_with_config / "config"
            # Use resolve() to handle macOS /var vs /private/var symlink
            assert ctx.config_path.resolve() == expected.resolve()


class TestOrgContextLazyServices:
    """Test lazy initialization of services."""

    def test_budget_service_lazy_init(self, org_with_config):
        """Should lazily initialize budget service."""
        with OrgContext.create(org_with_config) as ctx:
            # Access internal to verify not initialized
            assert ctx._budget_service is None

            # Access property - should initialize
            service = ctx.budget_service
            assert service is not None
            assert ctx._budget_service is not None

            # Second access should return same instance
            assert ctx.budget_service is service

    def test_storage_lazy_init(self, org_with_config):
        """Should lazily initialize storage manager."""
        with OrgContext.create(org_with_config) as ctx:
            assert ctx._storage_manager is None

            storage = ctx.storage
            assert storage is not None
            assert ctx._storage_manager is not None
            assert ctx.storage is storage

    def test_org_lazy_init(self, org_with_config):
        """Should lazily initialize Org wrapper."""
        with OrgContext.create(org_with_config) as ctx:
            assert ctx._org is None

            org = ctx.org
            assert org is not None
            assert ctx._org is not None
            assert ctx.org is org

    def test_bead_service_lazy_init(self, org_with_config):
        """Should lazily initialize bead service."""
        with OrgContext.create(org_with_config) as ctx:
            assert ctx._bead_service is None

            # Note: bead_service may raise FileNotFoundError if bd binary not found
            # That's expected in test environments without the bundled binary
            try:
                service = ctx.bead_service
                assert service is not None
                assert ctx._bead_service is not None
            except FileNotFoundError:
                # Expected if bd binary not bundled
                pass


class TestOrgContextManager:
    """Test context manager pattern."""

    def test_context_manager_closes_on_exit(self, org_with_config):
        """Should close resources when exiting context."""
        with OrgContext.create(org_with_config) as ctx:
            db = ctx.db
            assert not ctx._closed

        # After exit, should be closed
        assert ctx._closed

    def test_context_manager_closes_on_exception(self, org_with_config):
        """Should close resources even on exception."""
        try:
            with OrgContext.create(org_with_config) as ctx:
                raise ValueError("test error")
        except ValueError:
            pass

        assert ctx._closed

    def test_access_after_close_raises(self, org_with_config):
        """Should raise OrgContextError after close."""
        ctx = OrgContext.create(org_with_config)
        ctx.close()

        with pytest.raises(OrgContextError) as exc_info:
            _ = ctx.db
        assert "closed" in str(exc_info.value).lower()

    def test_double_close_is_safe(self, org_with_config):
        """Should handle double close gracefully."""
        ctx = OrgContext.create(org_with_config)
        ctx.close()
        ctx.close()  # Should not raise

    def test_close_clears_services(self, org_with_config):
        """Should clear service references on close."""
        with OrgContext.create(org_with_config) as ctx:
            # Initialize some services
            _ = ctx.budget_service
            _ = ctx.storage

        # After close, service references should be cleared
        assert ctx._budget_service is None
        assert ctx._storage_manager is None


class TestOrgContextIntegration:
    """Integration tests for OrgContext with services."""

    def test_budget_service_works(self, org_with_config):
        """Should be able to use budget service through context."""
        from core.queries import (
            create_team,
            create_worker,
            create_budget_pool,
        )

        with OrgContext.create(org_with_config) as ctx:
            # Set up test data
            team = create_team(ctx.db, "Engineering")
            ceo = create_worker(ctx.db, "Alice CEO", "CEO", team.id, 90)

            now = datetime.now()
            pool = create_budget_pool(
                ctx.db,
                name="Q1 Budget",
                total_credits=10000.0,
                period_start=now - timedelta(days=15),
                period_end=now + timedelta(days=15),
            )

            # Use budget service
            service = ctx.budget_service
            alloc_id = service.allocate_from_pool(
                pool_id=pool.id,
                worker_id=ceo.id,
                amount=5000.0,
                period_start=pool.period_start,
                period_end=pool.period_end,
                can_delegate=True,
            )

            # Verify allocation was created
            balance = service.get_balance(ceo.id)
            assert balance is not None
            assert balance.allocated == 5000.0

    def test_storage_works(self, org_with_config):
        """Should be able to use storage manager through context."""
        from core.queries import create_team, create_worker

        with OrgContext.create(org_with_config) as ctx:
            # Set up test data
            team = create_team(ctx.db, "Engineering")
            ceo = create_worker(ctx.db, "Alice CEO", "CEO", team.id, 90)

            # Use storage manager
            storage = ctx.storage
            worker_path = storage.ensure_worker_storage(ceo.id, reports_to="")

            assert worker_path.exists()
            assert storage.worker_storage_exists(ceo.id, reports_to="")

    def test_org_wrapper_works(self, org_with_config):
        """Should be able to use Org wrapper through context."""
        with OrgContext.create(org_with_config) as ctx:
            org = ctx.org

            # Org should be uninitialized
            assert org.status == "uninitialized"

            # Initialize org
            ceo = org.init("Test CEO", initial_budget=1000.0)
            assert ceo is not None
            assert org.status == "initialized"

    def test_database_transactions(self, org_with_config):
        """Should support database transactions through context."""
        from core.queries import create_team, get_team

        with OrgContext.create(org_with_config) as ctx:
            # Use transaction
            with ctx.db.transaction() as cursor:
                cursor.execute(
                    "INSERT INTO teams (id, name) VALUES (?, ?)",
                    ("team-test", "Test Team"),
                )

            # Verify committed
            team = get_team(ctx.db, "team-test")
            assert team is not None
            assert team.name == "Test Team"


class TestOrgContextEdgeCases:
    """Test edge cases and error handling."""

    def test_resolve_relative_path(self, org_with_config):
        """Should resolve relative paths to absolute."""
        # Get a relative version of the path
        import os

        cwd = Path.cwd()
        try:
            # Create relative path if possible
            relative = org_with_config.relative_to(cwd)
        except ValueError:
            # Can't make relative path, skip test
            pytest.skip("Cannot create relative path for test")

        with OrgContext.create(relative) as ctx:
            # Should have resolved to absolute
            assert ctx.org_path.is_absolute()
            assert ctx.org_path == org_with_config

    def test_services_share_database(self, org_with_config):
        """All services should share the same database instance."""
        with OrgContext.create(org_with_config) as ctx:
            # Access services
            budget = ctx.budget_service
            storage = ctx.storage
            org = ctx.org

            # All should use same db instance
            assert budget.db is ctx.db
            assert storage.db is ctx.db
            assert org.db is ctx.db

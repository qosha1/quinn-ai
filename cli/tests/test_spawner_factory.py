"""
Tests for SpawnerFactory.

Tests strategy registration, selection, and factory management.
"""

import pytest
from unittest.mock import MagicMock, patch

from core.sessions.spawner import SpawnStrategy, SpawnerConfig, SpawnResult
from core.sessions.spawner_factory import (
    SpawnerFactory,
    SpawnerNotFoundError,
    get_default_factory,
    set_default_factory,
    reset_default_factory,
)


class MockSpawner(SpawnStrategy):
    """Mock spawner for testing."""

    def __init__(self, name: str = "mock"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def spawn(self, config: SpawnerConfig) -> SpawnResult:
        return SpawnResult(success=True, pid=12345, session_id="mock-session")

    def stop(self, session_id: str, force: bool = False) -> bool:
        return True

    def is_alive(self, session_id: str) -> bool:
        return True

    def send_input(self, session_id: str, text: str) -> bool:
        return True

    def read_output(self, session_id: str, timeout_ms=None) -> str:
        return "mock output"


class AnotherMockSpawner(SpawnStrategy):
    """Another mock spawner for testing multiple registrations."""

    @property
    def name(self) -> str:
        return "another"

    def spawn(self, config: SpawnerConfig) -> SpawnResult:
        return SpawnResult(success=True, pid=54321, session_id="another-session")

    def stop(self, session_id: str, force: bool = False) -> bool:
        return True

    def is_alive(self, session_id: str) -> bool:
        return True

    def send_input(self, session_id: str, text: str) -> bool:
        return True

    def read_output(self, session_id: str, timeout_ms=None) -> str:
        return "another output"


class TestSpawnerFactory:
    """Tests for SpawnerFactory class."""

    def test_init_empty(self):
        """Should initialize with no spawners."""
        factory = SpawnerFactory()

        assert len(factory.list()) == 0
        assert factory.default is None
        assert factory.default_name is None

    def test_register_spawner(self):
        """Should register a spawner instance."""
        factory = SpawnerFactory()
        spawner = MockSpawner("test")

        factory.register(spawner)

        assert factory.has("test")
        assert factory.get("test") is spawner
        assert "test" in factory.list()

    def test_register_class(self):
        """Should register a spawner by class."""
        factory = SpawnerFactory()

        # Pass spawner constructor kwargs separately from registration name
        factory.register_class("test-spawner", MockSpawner, name="test")

        assert factory.has("test-spawner")
        spawner = factory.get("test-spawner")
        assert isinstance(spawner, MockSpawner)
        assert spawner.name == "test"

    def test_unregister_spawner(self):
        """Should unregister a spawner."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("test"))

        factory.unregister("test")

        assert not factory.has("test")
        assert "test" not in factory.list()

    def test_unregister_clears_default(self):
        """Should clear default when unregistering default spawner."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("test"))
        factory.set_default("test")

        factory.unregister("test")

        assert factory.default is None
        assert factory.default_name is None

    def test_unregister_nonexistent(self):
        """Should handle unregistering nonexistent spawner."""
        factory = SpawnerFactory()

        # Should not raise
        factory.unregister("nonexistent")

    def test_get_existing_spawner(self):
        """Should get registered spawner."""
        factory = SpawnerFactory()
        spawner = MockSpawner("test")
        factory.register(spawner)

        result = factory.get("test")

        assert result is spawner

    def test_get_nonexistent_raises(self):
        """Should raise SpawnerNotFoundError for unknown spawner."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("test"))

        with pytest.raises(SpawnerNotFoundError) as exc_info:
            factory.get("unknown")

        assert exc_info.value.name == "unknown"
        assert "test" in exc_info.value.available

    def test_has_returns_true_for_registered(self):
        """Should return True for registered spawner."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("test"))

        assert factory.has("test")

    def test_has_returns_false_for_unregistered(self):
        """Should return False for unregistered spawner."""
        factory = SpawnerFactory()

        assert not factory.has("unknown")

    def test_list_returns_all_names(self):
        """Should list all registered spawner names."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("test1"))
        factory.register(AnotherMockSpawner())

        names = factory.list()

        assert "test1" in names
        assert "another" in names
        assert len(names) == 2

    def test_set_default(self):
        """Should set default spawner."""
        factory = SpawnerFactory()
        spawner = MockSpawner("test")
        factory.register(spawner)

        factory.set_default("test")

        assert factory.default is spawner
        assert factory.default_name == "test"

    def test_set_default_nonexistent_raises(self):
        """Should raise SpawnerNotFoundError for unknown spawner."""
        factory = SpawnerFactory()

        with pytest.raises(SpawnerNotFoundError):
            factory.set_default("unknown")

    def test_get_for_config_with_explicit_strategy(self):
        """Should use strategy from config options."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("mock"))
        factory.register(AnotherMockSpawner())

        config = SpawnerConfig(
            command="test",
            options={"spawn_strategy": "another"},
        )

        spawner = factory.get_for_config(config)

        assert spawner.name == "another"

    def test_get_for_config_uses_default(self):
        """Should use default when no strategy in config."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("mock"))
        factory.register(AnotherMockSpawner())
        factory.set_default("mock")

        config = SpawnerConfig(command="test")

        spawner = factory.get_for_config(config)

        assert spawner.name == "mock"

    def test_get_for_config_uses_first_when_no_default(self):
        """Should use first available when no default set."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("mock"))

        config = SpawnerConfig(command="test")

        spawner = factory.get_for_config(config)

        assert spawner.name == "mock"

    def test_get_for_config_raises_when_empty(self):
        """Should raise when no spawners available."""
        factory = SpawnerFactory()
        config = SpawnerConfig(command="test")

        with pytest.raises(SpawnerNotFoundError):
            factory.get_for_config(config)

    def test_get_for_config_raises_when_strategy_not_found(self):
        """Should raise when explicit strategy not found."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("mock"))

        config = SpawnerConfig(
            command="test",
            options={"spawn_strategy": "unknown"},
        )

        with pytest.raises(SpawnerNotFoundError):
            factory.get_for_config(config)

    @patch("shutil.which")
    def test_register_defaults_subprocess_only(self, mock_which):
        """Should register subprocess when tmux unavailable."""
        mock_which.return_value = None  # tmux not found
        factory = SpawnerFactory()

        factory.register_defaults()

        assert factory.has("subprocess")
        assert not factory.has("tmux")
        assert factory.default_name == "subprocess"

    @patch("shutil.which")
    def test_register_defaults_with_tmux(self, mock_which):
        """Should register tmux when available."""
        mock_which.return_value = "/usr/bin/tmux"
        factory = SpawnerFactory()

        factory.register_defaults()

        assert factory.has("subprocess")
        assert factory.has("tmux")
        assert factory.default_name == "tmux"

    def test_register_multiple_spawners(self):
        """Should handle multiple spawner registrations."""
        factory = SpawnerFactory()
        factory.register(MockSpawner("mock1"))
        factory.register(MockSpawner("mock2"))
        factory.register(AnotherMockSpawner())

        assert len(factory.list()) == 3
        assert factory.has("mock1")
        assert factory.has("mock2")
        assert factory.has("another")


class TestSpawnerNotFoundError:
    """Tests for SpawnerNotFoundError exception."""

    def test_error_message(self):
        """Should have informative error message."""
        error = SpawnerNotFoundError("unknown", ["subprocess", "tmux"])

        assert "unknown" in str(error)
        assert "subprocess" in str(error)
        assert "tmux" in str(error)

    def test_attributes(self):
        """Should store name and available list."""
        error = SpawnerNotFoundError("bad", ["good1", "good2"])

        assert error.name == "bad"
        assert error.available == ["good1", "good2"]


class TestDefaultFactory:
    """Tests for default factory functions."""

    def setup_method(self):
        """Reset factory before each test."""
        reset_default_factory()

    def teardown_method(self):
        """Reset factory after each test."""
        reset_default_factory()

    @patch("shutil.which")
    def test_get_default_factory_lazy_init(self, mock_which):
        """Should lazily initialize default factory."""
        mock_which.return_value = None  # No tmux
        factory = get_default_factory()

        assert factory is not None
        assert isinstance(factory, SpawnerFactory)
        assert factory.has("subprocess")

    def test_get_default_factory_singleton(self):
        """Should return same instance on subsequent calls."""
        factory1 = get_default_factory()
        factory2 = get_default_factory()

        assert factory1 is factory2

    def test_set_default_factory(self):
        """Should allow setting custom default factory."""
        custom = SpawnerFactory()
        custom.register(MockSpawner("custom"))

        set_default_factory(custom)

        assert get_default_factory() is custom
        assert get_default_factory().has("custom")

    def test_reset_default_factory(self):
        """Should reset to None for lazy re-initialization."""
        initial = get_default_factory()

        reset_default_factory()
        set_default_factory(None)

        new = get_default_factory()
        assert new is not initial

    def test_default_factory_registers_defaults(self):
        """Should register default spawners on init."""
        factory = get_default_factory()

        # Should have at least subprocess
        assert factory.has("subprocess")
        assert factory.default is not None


class TestSpawnerFactoryIntegration:
    """Integration tests for SpawnerFactory."""

    def test_full_lifecycle(self):
        """Test complete factory lifecycle."""
        factory = SpawnerFactory()

        # Register spawners
        factory.register(MockSpawner("mock"))
        factory.register(AnotherMockSpawner())
        factory.set_default("mock")

        # Use for spawning
        config = SpawnerConfig(command="test", worker_id="worker-123")
        spawner = factory.get_for_config(config)
        result = spawner.spawn(config)

        assert result.success
        assert result.pid == 12345

        # Use explicit strategy
        config_explicit = SpawnerConfig(
            command="test",
            options={"spawn_strategy": "another"},
        )
        spawner2 = factory.get_for_config(config_explicit)
        result2 = spawner2.spawn(config_explicit)

        assert result2.success
        assert result2.pid == 54321

        # Unregister
        factory.unregister("mock")
        assert not factory.has("mock")
        assert factory.default is None

    def test_error_handling(self):
        """Test error handling across factory operations."""
        factory = SpawnerFactory()

        # Get nonexistent
        with pytest.raises(SpawnerNotFoundError):
            factory.get("nonexistent")

        # Set default nonexistent
        with pytest.raises(SpawnerNotFoundError):
            factory.set_default("nonexistent")

        # Get for config with empty factory
        config = SpawnerConfig(command="test")
        with pytest.raises(SpawnerNotFoundError):
            factory.get_for_config(config)

    def test_concurrent_access(self):
        """Test factory handles concurrent access."""
        import threading

        factory = SpawnerFactory()
        factory.register(MockSpawner("mock"))

        results = []

        def access_factory():
            for _ in range(100):
                spawner = factory.get("mock")
                results.append(spawner.name)

        threads = [threading.Thread(target=access_factory) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 500
        assert all(r == "mock" for r in results)

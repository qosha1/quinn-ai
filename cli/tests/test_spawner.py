"""
Tests for spawn strategies.
"""

import pytest
from pathlib import Path

from cli.core.sessions import (
    SpawnStrategy,
    SpawnerConfig,
    SpawnResult,
    SubprocessSpawner,
    TmuxSpawner,
    SpawnerFactory,
    SpawnerNotFoundError,
    get_default_factory,
    reset_default_factory,
)


class TestSpawnerConfig:
    """Tests for SpawnerConfig dataclass."""

    def test_basic_config(self):
        """Should create config with required fields."""
        config = SpawnerConfig(command="echo", args=["hello"])
        assert config.command == "echo"
        assert config.args == ["hello"]
        assert config.cols == 120
        assert config.rows == 40

    def test_config_with_all_fields(self):
        """Should create config with all fields."""
        config = SpawnerConfig(
            command="python",
            args=["-c", "print('test')"],
            working_directory=Path("/tmp"),
            env_vars={"FOO": "bar"},
            cols=80,
            rows=24,
            session_name="test-session",
            worker_id="worker-1",
            options={"spawn_strategy": "subprocess"},
        )
        assert config.command == "python"
        assert config.working_directory == Path("/tmp")
        assert config.env_vars == {"FOO": "bar"}
        assert config.session_name == "test-session"
        assert config.options["spawn_strategy"] == "subprocess"


class TestSubprocessSpawner:
    """Tests for SubprocessSpawner."""

    def test_spawner_name(self):
        """Should return correct name."""
        spawner = SubprocessSpawner()
        assert spawner.name == "subprocess"

    def test_spawn_echo(self):
        """Should spawn a simple command."""
        spawner = SubprocessSpawner()
        config = SpawnerConfig(command="echo", args=["hello"])

        result = spawner.spawn(config)

        assert result.success
        assert result.pid is not None
        assert result.session_id is not None
        assert result.error is None

        # Cleanup
        spawner.stop(result.session_id, force=True)

    def test_spawn_nonexistent_command(self):
        """Should fail gracefully for nonexistent command."""
        spawner = SubprocessSpawner()
        config = SpawnerConfig(command="nonexistent_command_xyz")

        result = spawner.spawn(config)

        assert not result.success
        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_is_alive(self):
        """Should correctly report process status."""
        spawner = SubprocessSpawner()
        # Use sleep for a long-running process
        config = SpawnerConfig(command="sleep", args=["10"])

        result = spawner.spawn(config)
        assert result.success

        # Should be alive
        assert spawner.is_alive(result.session_id)

        # Stop it
        spawner.stop(result.session_id, force=True)

        # Should not be alive
        assert not spawner.is_alive(result.session_id)

    def test_stop_graceful(self):
        """Should stop process gracefully."""
        spawner = SubprocessSpawner()
        config = SpawnerConfig(command="sleep", args=["100"])

        result = spawner.spawn(config)
        assert result.success

        stopped = spawner.stop(result.session_id, force=False)
        assert stopped
        assert not spawner.is_alive(result.session_id)

    def test_stop_force(self):
        """Should force stop process."""
        spawner = SubprocessSpawner()
        config = SpawnerConfig(command="sleep", args=["100"])

        result = spawner.spawn(config)
        assert result.success

        stopped = spawner.stop(result.session_id, force=True)
        assert stopped
        assert not spawner.is_alive(result.session_id)


class TestTmuxSpawner:
    """Tests for TmuxSpawner."""

    @pytest.fixture
    def spawner(self):
        """Create TmuxSpawner."""
        spawner = TmuxSpawner()
        yield spawner
        # Cleanup any sessions we created
        for session in spawner.list_sessions():
            if session.startswith("test-"):
                spawner.stop(session, force=True)

    def test_spawner_name(self):
        """Should return correct name."""
        spawner = TmuxSpawner()
        assert spawner.name == "tmux"

    @pytest.mark.skipif(
        not TmuxSpawner()._find_tmux(),
        reason="tmux not installed"
    )
    def test_spawn_and_stop(self, spawner):
        """Should spawn and stop tmux session."""
        config = SpawnerConfig(
            command="sleep",
            args=["100"],
            session_name="test-spawn-stop",
        )

        result = spawner.spawn(config)
        assert result.success
        assert result.session_id == "test-spawn-stop"

        # Should be alive
        assert spawner.is_alive(result.session_id)

        # Stop it
        stopped = spawner.stop(result.session_id, force=True)
        assert stopped

        # Should not be alive
        assert not spawner.is_alive(result.session_id)

    @pytest.mark.skipif(
        not TmuxSpawner()._find_tmux(),
        reason="tmux not installed"
    )
    def test_is_alive(self, spawner):
        """Should correctly report session status."""
        config = SpawnerConfig(
            command="sleep",
            args=["100"],
            session_name="test-is-alive",
        )

        result = spawner.spawn(config)
        assert result.success

        # Should be alive
        assert spawner.is_alive(result.session_id)

        # Stop it
        spawner.stop(result.session_id, force=True)

        # Should not be alive
        assert not spawner.is_alive(result.session_id)

    @pytest.mark.skipif(
        not TmuxSpawner()._find_tmux(),
        reason="tmux not installed"
    )
    def test_list_sessions(self, spawner):
        """Should list tmux sessions."""
        config = SpawnerConfig(
            command="sleep",
            args=["100"],
            session_name="test-list-sessions",
        )

        result = spawner.spawn(config)
        assert result.success

        sessions = spawner.list_sessions()
        assert "test-list-sessions" in sessions

        spawner.stop(result.session_id, force=True)


class TestSpawnerFactory:
    """Tests for SpawnerFactory."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset default factory after each test."""
        yield
        reset_default_factory()

    def test_register_and_get(self):
        """Should register and retrieve spawners."""
        factory = SpawnerFactory()
        spawner = SubprocessSpawner()

        factory.register(spawner)

        retrieved = factory.get("subprocess")
        assert retrieved is spawner

    def test_get_nonexistent(self):
        """Should raise error for nonexistent spawner."""
        factory = SpawnerFactory()

        with pytest.raises(SpawnerNotFoundError) as exc_info:
            factory.get("nonexistent")

        assert exc_info.value.name == "nonexistent"

    def test_has(self):
        """Should check if spawner is registered."""
        factory = SpawnerFactory()
        factory.register(SubprocessSpawner())

        assert factory.has("subprocess")
        assert not factory.has("nonexistent")

    def test_list(self):
        """Should list registered spawners."""
        factory = SpawnerFactory()
        factory.register(SubprocessSpawner())

        names = factory.list()
        assert "subprocess" in names

    def test_set_default(self):
        """Should set and get default spawner."""
        factory = SpawnerFactory()
        factory.register(SubprocessSpawner())
        factory.set_default("subprocess")

        assert factory.default_name == "subprocess"
        assert factory.default is not None
        assert factory.default.name == "subprocess"

    def test_register_defaults(self):
        """Should register default spawners."""
        factory = SpawnerFactory()
        factory.register_defaults()

        assert factory.has("subprocess")
        # tmux may or may not be available
        assert len(factory.list()) >= 1

    def test_get_for_config_explicit(self):
        """Should use explicit strategy from config."""
        factory = SpawnerFactory()
        factory.register(SubprocessSpawner())
        factory.set_default("subprocess")

        config = SpawnerConfig(
            command="echo",
            options={"spawn_strategy": "subprocess"},
        )

        spawner = factory.get_for_config(config)
        assert spawner.name == "subprocess"

    def test_get_for_config_default(self):
        """Should use default strategy when not specified."""
        factory = SpawnerFactory()
        factory.register(SubprocessSpawner())
        factory.set_default("subprocess")

        config = SpawnerConfig(command="echo")

        spawner = factory.get_for_config(config)
        assert spawner.name == "subprocess"

    def test_get_default_factory(self):
        """Should get/create default factory."""
        factory = get_default_factory()

        assert factory is not None
        assert factory.has("subprocess")

        # Should return same instance
        factory2 = get_default_factory()
        assert factory is factory2

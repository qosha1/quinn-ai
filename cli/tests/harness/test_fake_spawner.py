"""Red-phase tests for FakeSpawner (bead quinn-ai-k6r).

These tests pin down the FakeSpawner contract before implementation. Run
this file BEFORE fake_spawner.py exists — every test must fail with an
ImportError or AttributeError. After L1.3 implements the harness, these
must all pass.
"""

import pytest

from cli.core.sessions.spawner import SpawnerConfig, SpawnResult, SpawnStrategy
from cli.core.sessions.spawner_factory import (
    SpawnerFactory,
    get_default_factory,
    reset_default_factory,
)

# This import is THE seam the harness adds — these tests fail with
# ImportError until cli/tests/harness/fake_spawner.py exists.
from cli.tests.harness.fake_spawner import (  # noqa: E402
    FakeSpawner,
    with_fake_spawner,
)


@pytest.fixture(autouse=True)
def _reset_factory():
    yield
    reset_default_factory()


class TestFakeSpawnerContract:
    def test_implements_spawn_strategy_abc(self):
        spawner = FakeSpawner()
        assert isinstance(spawner, SpawnStrategy)

    def test_name_is_fake(self):
        assert FakeSpawner().name == "fake"

    def test_spawn_returns_success_result(self):
        spawner = FakeSpawner()
        result = spawner.spawn(SpawnerConfig(command="anything", worker_id="w1"))
        assert isinstance(result, SpawnResult)
        assert result.success is True
        assert result.session_id is not None

    def test_spawn_records_config(self):
        spawner = FakeSpawner()
        cfg = SpawnerConfig(command="hi", args=["--flag"], worker_id="w1")
        spawner.spawn(cfg)
        assert len(spawner.spawned) == 1
        assert spawner.spawned[0] is cfg

    def test_default_state_after_spawn_is_running(self):
        spawner = FakeSpawner()
        r = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        assert spawner.is_alive(r.session_id) is True
        assert spawner.get_state(r.session_id) == "running"

    def test_stop_marks_session_stopped(self):
        spawner = FakeSpawner()
        r = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        ok = spawner.stop(r.session_id)
        assert ok is True
        assert spawner.is_alive(r.session_id) is False
        assert spawner.get_state(r.session_id) == "stopped"

    def test_stop_unknown_session_returns_false(self):
        spawner = FakeSpawner()
        assert spawner.stop("does-not-exist") is False

    def test_send_input_records_calls(self):
        spawner = FakeSpawner()
        r = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        assert spawner.send_input(r.session_id, "hello") is True
        assert spawner.send_input(r.session_id, "world") is True
        assert spawner.inputs == [(r.session_id, "hello"), (r.session_id, "world")]

    def test_send_input_to_stopped_session_returns_false(self):
        spawner = FakeSpawner()
        r = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        spawner.stop(r.session_id)
        assert spawner.send_input(r.session_id, "anything") is False

    def test_read_output_returns_preloaded_text(self):
        spawner = FakeSpawner()
        r = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        spawner.set_output(r.session_id, "fake banner\nready\n")
        assert spawner.read_output(r.session_id) == "fake banner\nready\n"

    def test_set_state_overrides_runtime(self):
        spawner = FakeSpawner()
        r = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        spawner.set_state(r.session_id, "crashed")
        assert spawner.get_state(r.session_id) == "crashed"
        assert spawner.is_alive(r.session_id) is False

    def test_idle_is_alive_but_not_running(self):
        spawner = FakeSpawner()
        r = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        spawner.set_state(r.session_id, "idle")
        assert spawner.get_state(r.session_id) == "idle"
        assert spawner.is_alive(r.session_id) is True

    def test_independent_sessions(self):
        spawner = FakeSpawner()
        a = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        b = spawner.spawn(SpawnerConfig(command="x", worker_id="w2"))
        assert a.session_id != b.session_id
        spawner.stop(a.session_id)
        assert spawner.is_alive(a.session_id) is False
        assert spawner.is_alive(b.session_id) is True

    def test_session_ids_are_deterministic_ish(self):
        # Each FakeSpawner instance counts from 0; that's good enough
        spawner = FakeSpawner()
        a = spawner.spawn(SpawnerConfig(command="x", worker_id="w1"))
        b = spawner.spawn(SpawnerConfig(command="x", worker_id="w2"))
        # Just need them to be predictable strings, not literally "fake-0"
        assert isinstance(a.session_id, str) and a.session_id
        assert isinstance(b.session_id, str) and b.session_id


class TestFakeSpawnerFactoryIntegration:
    def test_can_register_in_a_factory(self):
        factory = SpawnerFactory()
        factory.register(FakeSpawner())
        assert factory.has("fake")
        spawner = factory.get("fake")
        assert isinstance(spawner, FakeSpawner)

    def test_with_fake_spawner_swaps_default_factory(self):
        # Before context: default factory has tmux/subprocess but not fake
        before = get_default_factory()
        assert not before.has("fake")
        with with_fake_spawner() as fake:
            inside = get_default_factory()
            assert inside.has("fake")
            # Yield value is the FakeSpawner instance, so tests can assert on it
            assert isinstance(fake, FakeSpawner)
        # After context: default factory is restored (no longer has 'fake')
        after = get_default_factory()
        assert not after.has("fake")

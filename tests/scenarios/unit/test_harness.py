"""ScenarioHarness — context manager that wires tmp dir + FakeSpawner."""
from pathlib import Path

import pytest

from shared.testing.scenarios import ScenarioHarness, ScenarioSpec


@pytest.fixture
def minimal_spec():
    return ScenarioSpec(
        name="empty",
        setup={"init": {}},
        ops=[],
        assertions=[],
    )


def test_creates_org_path_on_enter(minimal_spec):
    with ScenarioHarness(minimal_spec) as run:
        assert run.org_path.exists()
        assert run.org_path.is_dir()


def test_cleans_up_on_exit(minimal_spec):
    captured: list[Path] = []
    with ScenarioHarness(minimal_spec) as run:
        captured.append(run.org_path)
    # tmp path should be cleaned up
    assert not captured[0].exists()


def test_cleans_up_on_exception(minimal_spec):
    captured: list[Path] = []
    with pytest.raises(RuntimeError, match="boom"):
        with ScenarioHarness(minimal_spec) as run:
            captured.append(run.org_path)
            raise RuntimeError("boom")
    assert not captured[0].exists()


def test_runner_attribute_present(minimal_spec):
    from click.testing import CliRunner

    with ScenarioHarness(minimal_spec) as run:
        assert isinstance(run.runner, CliRunner)


def test_double_enter_rejected(minimal_spec):
    h = ScenarioHarness(minimal_spec)
    with h:
        with pytest.raises(RuntimeError):
            h.__enter__()


def test_fake_spawner_swapped_inside(minimal_spec):
    """While inside the harness, the spawner registry should yield FakeSpawner."""
    from cli.tests.harness.fake_spawner import FakeSpawner

    with ScenarioHarness(minimal_spec) as run:
        assert isinstance(run.spawner, FakeSpawner)

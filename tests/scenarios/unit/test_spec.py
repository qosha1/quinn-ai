"""ScenarioSpec — pure data with YAML loading + validation."""
from pathlib import Path

import pytest

from shared.testing.scenarios import ScenarioSpec


def test_construct_with_minimum_fields():
    spec = ScenarioSpec(name="x", setup={}, ops=[], assertions=[])
    assert spec.name == "x"


def test_immutable():
    spec = ScenarioSpec(name="x", setup={}, ops=[], assertions=[])
    with pytest.raises((AttributeError, TypeError)):
        spec.name = "y"


def test_from_yaml_roundtrip(tmp_path):
    yml = tmp_path / "s.yml"
    yml.write_text(
        """
name: minimal
setup:
  init:
    ceo_name: Alice
ops:
  - { op: hire, name: Bob, role: Manager, manager: ceo }
assertions:
  - { kind: worker_count, value: 2 }
"""
    )
    spec = ScenarioSpec.from_yaml(yml)
    assert spec.name == "minimal"
    assert spec.setup["init"]["ceo_name"] == "Alice"
    assert len(spec.ops) == 1
    assert spec.ops[0]["op"] == "hire"
    assert len(spec.assertions) == 1


def test_from_yaml_rejects_unknown_op_kind(tmp_path):
    yml = tmp_path / "s.yml"
    yml.write_text(
        """
name: bad
setup: {}
ops:
  - { op: nonexistent_thing }
assertions: []
"""
    )
    with pytest.raises(ValueError, match="unknown op kind"):
        ScenarioSpec.from_yaml(yml)


def test_from_yaml_rejects_unknown_assertion_kind(tmp_path):
    yml = tmp_path / "s.yml"
    yml.write_text(
        """
name: bad
setup: {}
ops: []
assertions:
  - { kind: unknown_check }
"""
    )
    with pytest.raises(ValueError, match="unknown assertion kind"):
        ScenarioSpec.from_yaml(yml)


def test_from_yaml_rejects_missing_required_fields(tmp_path):
    yml = tmp_path / "s.yml"
    yml.write_text("name: x\n")  # missing setup/ops/assertions
    with pytest.raises(ValueError):
        ScenarioSpec.from_yaml(yml)

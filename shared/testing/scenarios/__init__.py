"""Scenario test framework — drive QuinnAI in-process via Click + FakeSpawner.

Public API:
    ScenarioSpec, ScenarioHarness, ScenarioRun
    OPS, PREDICATES — registries; add new ops or predicates by registering callables here.
"""
from .harness import ScenarioHarness, ScenarioRun
from .ops import OPS
from .predicates import PREDICATES
from .spec import ScenarioSpec

__all__ = [
    "OPS",
    "PREDICATES",
    "ScenarioHarness",
    "ScenarioRun",
    "ScenarioSpec",
]

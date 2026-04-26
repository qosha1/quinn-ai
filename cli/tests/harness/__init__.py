"""Reusable test harnesses for QuinnAI CLI tests.

Layer 1 — FakeSpawner (no tmux needed): see fake_spawner.py
Layer 2 — Real tmux + fake CLI: see tmux_fixtures.py + fake_cli.py
"""

from .fake_spawner import FakeSpawner, with_fake_spawner
from .fake_session import FakeSession, with_fake_session_registry

__all__ = [
    "FakeSpawner",
    "with_fake_spawner",
    "FakeSession",
    "with_fake_session_registry",
]

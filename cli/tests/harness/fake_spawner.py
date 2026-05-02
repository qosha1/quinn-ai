"""FakeSpawner — in-memory SpawnStrategy double for tests.

Layer 1 of the audit-coverage harness (bead quinn-ai-okw). Lets tests
exercise the parts of QuinnAI that need 'a session exists for this
worker' without spawning a real process or tmux session.

Usage in a test::

    from cli.tests.harness import with_fake_spawner

    def test_hire_binds_session():
        with with_fake_spawner() as fake:
            # ... drive `qn org hire` here ...
            assert len(fake.spawned) == 1
            assert fake.spawned[0].worker_id is not None

The FakeSpawner is registered into the global SpawnerFactory under the
name 'fake' for the duration of the context, and the previous factory
is restored on exit.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Literal, Optional

from cli.core.sessions.spawner import (
    SpawnerConfig,
    SpawnResult,
    SpawnStrategy,
)
from cli.core.sessions.spawner_factory import (
    SpawnerFactory,
    reset_default_factory,
    set_default_factory,
)


SessionState = Literal["running", "idle", "stopped", "crashed"]


@dataclass
class _FakeSession:
    state: SessionState = "running"
    output: str = ""


class FakeSpawner(SpawnStrategy):
    """In-memory SpawnStrategy. Records all calls; state is programmable."""

    def __init__(self, prefix: str = "fake"):
        self._prefix = prefix
        self._counter = 0
        self._sessions: dict[str, _FakeSession] = {}

        # Recorded interactions — tests assert against these.
        self.spawned: list[SpawnerConfig] = []
        self.inputs: list[tuple[str, str]] = []
        self.stops: list[tuple[str, bool]] = []

    # --- SpawnStrategy ABC ---

    @property
    def name(self) -> str:
        return "fake"

    def spawn(self, config: SpawnerConfig) -> SpawnResult:
        self._counter += 1
        sid = f"{self._prefix}-{self._counter:04d}"
        self._sessions[sid] = _FakeSession()
        # Record the config as-is. working_directory is set by the caller
        # using resolve_session_cwd (host-mode aware) before reaching here.
        # Scenario tests can assert on spawned[i].working_directory to verify
        # host-mode produces project_root cwd (quinn-ai-jofi).
        self.spawned.append(config)
        return SpawnResult(success=True, pid=10000 + self._counter, session_id=sid)

    def stop(self, session_id: str, force: bool = False) -> bool:
        self.stops.append((session_id, force))
        sess = self._sessions.get(session_id)
        if sess is None:
            return False
        sess.state = "stopped"
        return True

    def is_alive(self, session_id: str) -> bool:
        sess = self._sessions.get(session_id)
        return sess is not None and sess.state in ("running", "idle")

    def send_input(self, session_id: str, text: str) -> bool:
        self.inputs.append((session_id, text))
        sess = self._sessions.get(session_id)
        if sess is None or sess.state in ("stopped", "crashed"):
            return False
        return True

    def read_output(self, session_id: str, timeout_ms: Optional[int] = None) -> str:
        sess = self._sessions.get(session_id)
        return sess.output if sess else ""

    # --- Test-only controls ---

    def get_state(self, session_id: str) -> Optional[SessionState]:
        sess = self._sessions.get(session_id)
        return sess.state if sess else None

    def set_state(self, session_id: str, state: SessionState) -> None:
        if session_id not in self._sessions:
            raise KeyError(f"unknown fake session: {session_id}")
        self._sessions[session_id].state = state

    def set_output(self, session_id: str, text: str) -> None:
        if session_id not in self._sessions:
            raise KeyError(f"unknown fake session: {session_id}")
        self._sessions[session_id].output = text

    def reset(self) -> None:
        self._counter = 0
        self._sessions.clear()
        self.spawned.clear()
        self.inputs.clear()
        self.stops.clear()


@contextmanager
def with_fake_spawner() -> Iterator[FakeSpawner]:
    """Replace the default SpawnerFactory with one that has a FakeSpawner.

    Yields the FakeSpawner instance so tests can assert on calls and
    drive state. Restores the default factory on exit (next caller gets
    a fresh default — no 'fake' adapter leaks across tests).
    """
    fake = FakeSpawner()
    factory = SpawnerFactory()
    factory.register_defaults()
    factory.register(fake)
    set_default_factory(factory)
    try:
        yield fake
    finally:
        reset_default_factory()

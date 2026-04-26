"""FakeSession — in-memory SessionInterface adapter for tests.

This is the layer that actually closes the audit gaps for the deferred
beads. The hire / start / pause / resume / fire flows all reach the
SessionInterface via SessionRegistry, NOT the lower-level SpawnerFactory.

Usage::

    from cli.tests.harness import with_fake_session_registry

    def test_hire_binds_session(initialized_org):
        with with_fake_session_registry() as fake_factory:
            # ... drive `qn org hire ... --provider fake` here ...
            sessions = fake_factory.created_sessions
            assert len(sessions) == 1
            assert sessions[0].config.worker_id == ...

The fake registers under provider name 'fake'; tests can also register
it under any other name (e.g. 'claude_code') to intercept the default
codepath without changing CLI args.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Literal, Optional, TYPE_CHECKING

from cli.core.session import (
    SessionConfig,
    SessionInterface,
    SessionOutput,
    SessionSpawnError,
)
from cli.core.sessions import registry as registry_module
from cli.core.sessions.registry import SessionRegistry

if TYPE_CHECKING:
    from shared.pyterm.state_monitor import StateMonitor


SessionRuntime = Literal["spawning", "running", "idle", "stopped", "crashed"]


class FakeSession(SessionInterface):
    """In-memory SessionInterface that spawns instantly without a real process.

    Records every input sent, every termination, and exposes hooks for
    tests to set state, simulate crashes, or preload read_output content.
    """

    # Class-level shared registry of created instances so a context manager
    # can collect them after a swap. (Each instance still has its own state.)
    _factory_log: list["FakeSession"] = []

    def __init__(self, config: SessionConfig):
        super().__init__(config)
        self._fake_pid: Optional[int] = None
        self._inputs_sent: list[str] = []
        self._terminate_called = False
        self._force_terminate = False
        self._spawn_called = False
        self._should_fail_spawn = False
        self._mock_output_buffer = ""
        # Auto-register every instance so factory-style tests can collect them.
        FakeSession._factory_log.append(self)

    # --- Test-only controls ---

    @classmethod
    def reset_log(cls) -> None:
        cls._factory_log.clear()

    @classmethod
    def created(cls) -> list["FakeSession"]:
        return list(cls._factory_log)

    def set_should_fail_spawn(self, should_fail: bool = True) -> None:
        self._should_fail_spawn = should_fail

    def set_output(self, text: str) -> None:
        self._mock_output_buffer = text

    @property
    def inputs_sent(self) -> list[str]:
        return list(self._inputs_sent)

    @property
    def terminate_was_called(self) -> bool:
        return self._terminate_called

    # --- Required abstract method implementations ---

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def pid(self) -> Optional[int]:
        return self._fake_pid

    def _spawn_process(self) -> None:
        if self._should_fail_spawn:
            raise SessionSpawnError(self._id, "fake spawn failure (set via set_should_fail_spawn)")
        self._spawn_called = True
        self._fake_pid = 99000

    def _terminate_process(self, force: bool = False) -> None:
        self._terminate_called = True
        self._force_terminate = force
        self._fake_pid = None

    def _send_input(self, text: str) -> None:
        self._inputs_sent.append(text)

    def _read_output(self, timeout_ms: Optional[int] = None) -> SessionOutput:
        return SessionOutput(content=self._mock_output_buffer, timestamp=datetime.now())

    def _detect_ready(self, output: str) -> bool:
        # Fake sessions are immediately ready.
        return True

    def _detect_completion(self, output: str) -> bool:
        return False

    def _get_context_usage(self) -> int:
        return 0

    def _send_interrupt(self) -> None:
        # No-op for fake.
        pass

    def _create_state_monitor(self) -> Optional["StateMonitor"]:
        # No background monitor for fake — tests drive state explicitly.
        return None


@contextmanager
def with_fake_session_registry(
    *,
    intercept_providers: tuple[str, ...] = ("fake", "claude_code", "codex", "gemini", "openai"),
) -> Iterator[type[FakeSession]]:
    """Replace the default SessionRegistry with one whose adapters are all FakeSession.

    By default also intercepts the standard provider names so existing
    code paths that pass `provider="claude_code"` still work without
    touching tmux.

    Yields the FakeSession class so tests can call FakeSession.created()
    to inspect spawned instances.
    """
    FakeSession.reset_log()
    # Stash + replace
    prev = registry_module._default_registry
    fake_registry = SessionRegistry()
    for name in intercept_providers:
        fake_registry.register(name, FakeSession)
    registry_module._default_registry = fake_registry
    try:
        yield FakeSession
    finally:
        registry_module._default_registry = prev
        FakeSession.reset_log()

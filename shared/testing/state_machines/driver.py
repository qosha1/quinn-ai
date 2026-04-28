"""TransitionDriver: pure state-graph walker."""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


class InvalidTransition(ValueError):
    """Raised when apply() is called with a target the current state cannot transition to."""

    def __init__(self, from_state: str, target: str, allowed: tuple[str, ...]):
        self.from_state = from_state
        self.target = target
        self.allowed = allowed
        super().__init__(
            f"invalid transition: {from_state!r} -> {target!r} "
            f"(allowed from {from_state!r}: {list(allowed) or '∅'})"
        )


class TransitionDriver:
    """Stateful walker over a transition graph.

    The graph is a `dict[str, list[str]]` where keys are states and values are
    the list of states each one can transition to. The driver holds a current
    state and validates apply() calls against it.

    No I/O, no global state. Independent of any concrete domain.
    """

    __slots__ = ("_transitions", "_state")

    def __init__(self, transitions: Mapping[str, list[str]], initial: str) -> None:
        if initial not in transitions:
            raise ValueError(
                f"initial state {initial!r} not in transitions table "
                f"(known states: {sorted(transitions.keys())})"
            )
        # Freeze: each adjacency list becomes a tuple, the dict itself becomes a
        # read-only mapping. Prevents callers from mutating our view of the graph.
        frozen = {k: tuple(v) for k, v in transitions.items()}
        self._transitions: Mapping[str, tuple[str, ...]] = MappingProxyType(frozen)
        self._state = initial

    @property
    def state(self) -> str:
        return self._state

    @property
    def transitions(self) -> Mapping[str, tuple[str, ...]]:
        return self._transitions

    def can_transition(self, target: str) -> bool:
        return target in self._transitions.get(self._state, ())

    def apply(self, target: str) -> None:
        allowed = self._transitions.get(self._state, ())
        if target not in allowed:
            raise InvalidTransition(self._state, target, allowed)
        self._state = target

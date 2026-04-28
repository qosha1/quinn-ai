"""Invariant checking over a set of named drivers."""
from __future__ import annotations

from typing import Callable, Mapping

from .driver import TransitionDriver
from .reachability import reachable_states, states_reaching, terminal_states


Invariant = Callable[[Mapping[str, TransitionDriver]], str | None]


def check(drivers: Mapping[str, TransitionDriver], invariants: list[Invariant]) -> list[str]:
    """Run every invariant against the current driver set; return violation messages.

    An invariant is any callable that takes the drivers mapping and returns
    None when satisfied or a descriptive string when violated. An empty
    return list means all invariants passed.
    """
    violations: list[str] = []
    for inv in invariants:
        msg = inv(drivers)
        if msg is not None:
            violations.append(msg)
    return violations


def all_states_reachable_from(initial: str) -> Invariant:
    """Invariant: every state in every driver's graph is reachable from `initial`.

    Checks against EACH driver in the set independently — so the same initial
    state name must exist in every driver's transition table for this to fire
    cleanly. Most often you'd run this once per machine.
    """

    def _impl(drivers: Mapping[str, TransitionDriver]) -> str | None:
        for name, driver in drivers.items():
            transitions = driver.transitions
            if initial not in transitions:
                continue  # invariant is N/A for this driver
            reached = reachable_states(transitions, initial)
            all_states = set(transitions.keys())
            orphans = all_states - reached
            if orphans:
                return (
                    f"{name}: states unreachable from {initial!r}: "
                    f"{sorted(orphans)}"
                )
        return None

    return _impl


def no_orphan_terminal_paths() -> Invariant:
    """Invariant: every state can reach at least one terminal state.

    Useful for lifecycle-style machines. Pure-cyclic machines (runtime, org)
    legitimately have no terminals; in that case this invariant flags them —
    only apply it where you expect a terminal to exist.
    """

    def _impl(drivers: Mapping[str, TransitionDriver]) -> str | None:
        for name, driver in drivers.items():
            transitions = driver.transitions
            terminals = terminal_states(transitions)
            if not terminals:
                return f"{name}: no terminal state in graph"
            # Every state must reach at least one terminal.
            can_reach_any = set()
            for term in terminals:
                can_reach_any |= states_reaching(transitions, term)
            stranded = set(transitions.keys()) - can_reach_any
            if stranded:
                return f"{name}: states cannot reach any terminal: {sorted(stranded)}"
        return None

    return _impl


def cross_machine_invariant(
    name: str,
    predicate: Callable[[Mapping[str, TransitionDriver]], bool],
    message: str,
) -> Invariant:
    """Build an invariant from a predicate over the full drivers mapping.

    Use this for rules that span multiple state machines, e.g. "runtime can
    only be `running` if lifecycle is in {onboarding, active}".

    `predicate` returns True when the invariant holds. The returned invariant
    yields `f"{name}: {message}"` when the predicate fails.
    """

    def _impl(drivers: Mapping[str, TransitionDriver]) -> str | None:
        if predicate(drivers):
            return None
        return f"{name}: {message}"

    return _impl

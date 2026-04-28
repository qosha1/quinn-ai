"""Reachability helpers — pure BFS over transition graphs."""
from __future__ import annotations

from collections import deque
from typing import Mapping


def reachable_states(transitions: Mapping[str, list[str] | tuple[str, ...]], initial: str) -> set[str]:
    """BFS forward from `initial`. Returns every state that can be reached."""
    if initial not in transitions:
        raise ValueError(f"initial state {initial!r} not in transitions table")
    seen: set[str] = {initial}
    queue: deque[str] = deque([initial])
    while queue:
        current = queue.popleft()
        for nxt in transitions.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def states_reaching(transitions: Mapping[str, list[str] | tuple[str, ...]], target: str) -> set[str]:
    """BFS backward to `target`. Returns every state that can eventually reach it."""
    # Build reverse adjacency
    reverse: dict[str, list[str]] = {k: [] for k in transitions}
    for src, dests in transitions.items():
        for dst in dests:
            reverse.setdefault(dst, []).append(src)

    if target not in reverse:
        return set()

    seen: set[str] = {target}
    queue: deque[str] = deque([target])
    while queue:
        current = queue.popleft()
        for prev in reverse.get(current, []):
            if prev not in seen:
                seen.add(prev)
                queue.append(prev)
    return seen


def can_reach(transitions: Mapping[str, list[str] | tuple[str, ...]], src: str, dst: str) -> bool:
    """True if `dst` is reachable from `src` via zero or more transitions."""
    if src not in transitions:
        return False
    return dst in reachable_states(transitions, src)


def terminal_states(transitions: Mapping[str, list[str] | tuple[str, ...]]) -> set[str]:
    """States with no outgoing transitions."""
    return {state for state, dests in transitions.items() if not dests}

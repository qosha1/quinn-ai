"""Generic state-machine sequence + invariant testing.

Public API:
    TransitionDriver, InvalidTransition
    Step, StepResult, run_sequence
    check, Invariant
    all_states_reachable_from, no_orphan_terminal_paths, cross_machine_invariant
    reachable_states, states_reaching, can_reach, terminal_states

This package depends on stdlib only and never imports from cli/, board_ui/,
or shared.state_machines. Bridge tests live in tests/state_sequences/test_real_sms.py.
"""
from .driver import InvalidTransition, TransitionDriver
from .invariants import (
    Invariant,
    all_states_reachable_from,
    check,
    cross_machine_invariant,
    no_orphan_terminal_paths,
)
from .reachability import (
    can_reach,
    reachable_states,
    states_reaching,
    terminal_states,
)
from .runner import Step, StepResult, run_sequence

__all__ = [
    "InvalidTransition",
    "Invariant",
    "Step",
    "StepResult",
    "TransitionDriver",
    "all_states_reachable_from",
    "can_reach",
    "check",
    "cross_machine_invariant",
    "no_orphan_terminal_paths",
    "reachable_states",
    "run_sequence",
    "states_reaching",
    "terminal_states",
]

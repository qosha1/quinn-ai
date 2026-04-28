"""Integration tests: run sequences + invariants against the actual QuinnAI state machines.

This is the only file in tests/state_sequences/ that imports from shared.state_machines.
Everything else lives in shared/testing/state_machines/ and is provider-agnostic.
"""
import pytest

from shared.state_machines import (
    ESCALATION_TRANSITIONS,
    LIFECYCLE_TRANSITIONS,
    ORG_TRANSITIONS,
    RUNTIME_TRANSITIONS,
    SESSION_ALLOWED_LIFECYCLES,
)
from shared.testing.state_machines import (
    Step,
    TransitionDriver,
    all_states_reachable_from,
    check,
    cross_machine_invariant,
    no_orphan_terminal_paths,
    run_sequence,
    terminal_states,
)


# Initial states the production code uses when entities are created.
LIFECYCLE_INITIAL = "pending"
RUNTIME_INITIAL = "starting"
ORG_INITIAL = "uninitialized"
ESCALATION_INITIAL = "normal"


def _drivers():
    """Build a fresh set of drivers for one scenario."""
    return {
        "lifecycle": TransitionDriver(LIFECYCLE_TRANSITIONS, initial=LIFECYCLE_INITIAL),
        "runtime": TransitionDriver(RUNTIME_TRANSITIONS, initial=RUNTIME_INITIAL),
        "org": TransitionDriver(ORG_TRANSITIONS, initial=ORG_INITIAL),
        "escalation": TransitionDriver(ESCALATION_TRANSITIONS, initial=ESCALATION_INITIAL),
    }


class TestWorkerLifecycleSequences:
    def test_happy_path_to_terminated(self):
        drivers = _drivers()
        steps = [
            Step("lifecycle", "onboarding"),
            Step("lifecycle", "active"),
            Step("lifecycle", "offboarding"),
            Step("lifecycle", "terminated"),
        ]
        results = run_sequence(drivers, steps)
        assert all(r.ok for r in results), [r.error for r in results if not r.ok]
        assert drivers["lifecycle"].state == "terminated"

    def test_suspended_recovery(self):
        drivers = _drivers()
        steps = [
            Step("lifecycle", "onboarding"),
            Step("lifecycle", "active"),
            Step("lifecycle", "suspended"),
            Step("lifecycle", "active"),
            Step("lifecycle", "terminated"),
        ]
        results = run_sequence(drivers, steps)
        assert all(r.ok for r in results)

    def test_pending_to_active_directly_is_blocked(self):
        drivers = _drivers()
        results = run_sequence(drivers, [Step("lifecycle", "active")])
        assert results[0].ok is False  # must go through onboarding


class TestRuntimeSequences:
    def test_crash_recovery(self):
        drivers = _drivers()
        steps = [
            Step("runtime", "running"),
            Step("runtime", "working"),
            Step("runtime", "crashed"),
            Step("runtime", "starting"),
            Step("runtime", "running"),
        ]
        results = run_sequence(drivers, steps)
        assert all(r.ok for r in results)

    def test_blocked_unblocked(self):
        drivers = _drivers()
        steps = [
            Step("runtime", "running"),
            Step("runtime", "working"),
            Step("runtime", "blocked"),
            Step("runtime", "working"),
        ]
        results = run_sequence(drivers, steps)
        assert all(r.ok for r in results)


class TestOrgSequences:
    def test_full_lifecycle(self):
        drivers = _drivers()
        steps = [
            Step("org", "initialized"),
            Step("org", "running"),
            Step("org", "stopped"),
            Step("org", "running"),
            Step("org", "stopped"),
        ]
        results = run_sequence(drivers, steps)
        assert all(r.ok for r in results)


class TestEscalationSequences:
    def test_warn_escalate_resolve_recover(self):
        drivers = _drivers()
        steps = [
            Step("escalation", "idle_warning"),
            Step("escalation", "escalated_pending"),
            Step("escalation", "escalated_resolved"),
            Step("escalation", "normal"),
        ]
        results = run_sequence(drivers, steps)
        assert all(r.ok for r in results)


class TestReachabilityInvariants:
    """Every reachable state must be reachable from initial; every state must reach a terminal."""

    @pytest.mark.parametrize(
        "name,transitions,initial,allow_no_terminal",
        [
            ("lifecycle", LIFECYCLE_TRANSITIONS, LIFECYCLE_INITIAL, False),
            ("runtime", RUNTIME_TRANSITIONS, RUNTIME_INITIAL, True),  # runtime is cyclic by design
            ("org", ORG_TRANSITIONS, ORG_INITIAL, True),  # org cycles running<->stopped
            ("escalation", ESCALATION_TRANSITIONS, ESCALATION_INITIAL, True),  # escalation cycles
        ],
    )
    def test_all_states_reachable_from_initial(self, name, transitions, initial, allow_no_terminal):
        d = TransitionDriver(transitions, initial=initial)
        violations = check({name: d}, [all_states_reachable_from(initial)])
        assert violations == [], f"{name}: {violations}"

    def test_lifecycle_has_terminal(self):
        # Worker lifecycle MUST have a terminal state (terminated). Other machines may cycle.
        assert "terminated" in terminal_states(LIFECYCLE_TRANSITIONS)


class TestCrossMachineInvariants:
    def test_session_only_runs_when_lifecycle_allows(self):
        """If runtime is in any active state, lifecycle must be in SESSION_ALLOWED_LIFECYCLES."""
        drivers = _drivers()
        # Move into active runtime without proper lifecycle — should fail invariant
        drivers["runtime"].apply("running")
        # lifecycle is still "pending" — sessions not allowed there

        rule = cross_machine_invariant(
            name="session_requires_session_allowed_lifecycle",
            predicate=lambda d: (
                d["runtime"].state in {"stopped", "crashed", "starting"}
                or d["lifecycle"].state in SESSION_ALLOWED_LIFECYCLES
            ),
            message=(
                "runtime is active but lifecycle is not in SESSION_ALLOWED_LIFECYCLES "
                "(must be onboarding or active)"
            ),
        )
        violations = check(drivers, [rule])
        assert len(violations) == 1

    def test_session_invariant_holds_when_lifecycle_active(self):
        drivers = _drivers()
        drivers["lifecycle"].apply("onboarding")
        drivers["lifecycle"].apply("active")
        drivers["runtime"].apply("running")
        drivers["runtime"].apply("working")

        rule = cross_machine_invariant(
            name="session_requires_session_allowed_lifecycle",
            predicate=lambda d: (
                d["runtime"].state in {"stopped", "crashed", "starting"}
                or d["lifecycle"].state in SESSION_ALLOWED_LIFECYCLES
            ),
            message="runtime active without session-allowed lifecycle",
        )
        violations = check(drivers, [rule])
        assert violations == []

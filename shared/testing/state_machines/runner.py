"""SequenceRunner: apply ordered steps across a set of named drivers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .driver import InvalidTransition, TransitionDriver


@dataclass(frozen=True, slots=True)
class Step:
    machine: str
    target: str


@dataclass(frozen=True, slots=True)
class StepResult:
    step: Step
    ok: bool
    from_state: str
    to_state: str
    error: str | None


def run_sequence(
    drivers: Mapping[str, TransitionDriver],
    steps: list[Step],
    *,
    halt: bool = True,
) -> list[StepResult]:
    """Apply each step to its named driver in order.

    Returns one StepResult per attempted step. By default, halts on the first
    failed step (subsequent steps are not attempted). Pass halt=False to keep
    going and collect all violations.
    """
    results: list[StepResult] = []
    for step in steps:
        driver = drivers.get(step.machine)
        if driver is None:
            results.append(
                StepResult(
                    step=step,
                    ok=False,
                    from_state="",
                    to_state="",
                    error=f"unknown machine: {step.machine!r}",
                )
            )
            if halt:
                break
            continue

        from_state = driver.state
        try:
            driver.apply(step.target)
        except InvalidTransition as e:
            results.append(
                StepResult(
                    step=step,
                    ok=False,
                    from_state=from_state,
                    to_state=from_state,
                    error=str(e),
                )
            )
            if halt:
                break
            continue

        results.append(
            StepResult(
                step=step,
                ok=True,
                from_state=from_state,
                to_state=driver.state,
                error=None,
            )
        )
    return results

"""Click decorator for wiring CLI commands into the board-rules engine.

Per quinn-ai-zm8a §4 + p286 §1: the decorator mirrors the existing
`requires_permission` pattern at cli/core/permissions/access_control.py.
It attaches `--justify` and `--override` Click options programmatically so
each rule-aware command doesn't need 2 boilerplate option lines.

Decorator stacking (zm8a §5): permissions decorator goes OUTSIDE the rule
check so unauthorized workers never trigger rule evaluation.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

import click

from cli.core.rules.types import DecisionKind
from shared.exceptions import RuleViolation


def evaluate_or_raise(
    ctx: Any,
    action: str,
    context: dict[str, Any],
    *,
    justify_bead_id: str | None = None,
    override_bead_id: str | None = None,
) -> None:
    """Evaluate the action against the rules engine on ctx.obj.

    On BLOCK-class decisions (BLOCK / REQUIRES_JUSTIFY / REQUIRES_OVERRIDE),
    raises click.ClickException with the rule's message + remediation.
    On ALLOW / ALLOW_WITH_NUDGE, returns silently. ALLOW_WITH_NUDGE prints
    the rule's nudge to stderr per t2zb §1 SUGGESTED behavior.
    """
    engine = ctx.obj.rules
    decision = engine.evaluate(
        action,
        context,
        justify_bead_id=justify_bead_id,
        override_bead_id=override_bead_id,
    )

    if decision.kind == DecisionKind.ALLOW:
        return
    if decision.kind == DecisionKind.ALLOW_WITH_NUDGE:
        click.echo(decision.message, err=True)
        return

    # BLOCK / REQUIRES_JUSTIFY / REQUIRES_OVERRIDE — refuse the action.
    msg = decision.message
    if decision.remediation:
        msg = f"{msg}\n{decision.remediation}"
    raise click.ClickException(msg)


def _build_action_context(
    ctx: Any,
    action: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Build the action context dict that the engine evaluates against.

    Per t2zb §C.1: keys include worker_id, worker_role, worker_role_level,
    env, args (flattened), body, target_paths.
    """
    import os as _os
    org_ctx = getattr(ctx, "obj", None)
    worker_id = getattr(org_ctx, "worker_id", None) or _os.environ.get("QUINN_WORKER_ID")

    # Body extraction: prefer common click param names that ship free text.
    body = (
        kwargs.get("body")
        or kwargs.get("message")
        or kwargs.get("description")
        or kwargs.get("notes")
        or ""
    )

    return {
        "worker_id": worker_id,
        "worker_role": kwargs.get("_role"),
        "worker_role_level": kwargs.get("_role_level"),
        "env": kwargs.get("_env", "dev"),
        "args": dict(kwargs),
        "body": body,
        "target_paths": kwargs.get("_target_paths", []) or [],
        "command": " ".join(str(a) for a in args),
    }


def requires_rule_check(action: str) -> Callable[[Callable], Callable]:
    """Click decorator: invoke the rules engine before the wrapped command runs.

    Programmatically attaches `--justify <bead-id>` and `--override <bead-id>`
    Click options so the decorated command doesn't need to declare them.
    Pops both flags from kwargs before calling the wrapped function so the
    command body is unaware of the rule-system plumbing.

    Apply INSIDE @requires_permission (auth gate runs first):

        @click.command()
        @requires_permission(...)
        @requires_rule_check("qn-org.fire")
        @pass_context
        def fire_cmd(ctx, ...):
            ...
    """

    def decorator(f: Callable) -> Callable:
        # Attach the click options programmatically (per zm8a §8).
        f = click.option(
            "--justify",
            "justify_bead",
            default=None,
            help="Bead ID with the supporting artifact for ENCOURAGED rules.",
        )(f)
        f = click.option(
            "--override",
            "override_bead",
            default=None,
            help="Approved override-request bead ID for REQUIRED rules.",
        )(f)

        @functools.wraps(f)
        @click.pass_context
        def wrapper(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
            justify = kwargs.pop("justify_bead", None)
            override = kwargs.pop("override_bead", None)

            action_context = _build_action_context(ctx, action, args, kwargs)
            evaluate_or_raise(
                ctx,
                action,
                action_context,
                justify_bead_id=justify,
                override_bead_id=override,
            )

            return f(*args, **kwargs)

        return wrapper

    return decorator

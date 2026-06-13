"""CLI entry point for the qn-bd command.

Wraps the bd (beads) CLI with org context, passing org path and worker ID
to provide permission-aware beads operations for QuinnAI workers.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from cli.core.bd_wrapper import BeadPermissionError, run_bd
from cli.core.lifecycle import LifecycleError


_TMUX_SESSION_PATTERN = re.compile(r"^qn-(wrkr-[a-zA-Z0-9_-]+)$")


def _resolve_from_tmux() -> tuple[Optional[str], Optional[str]]:
    """Recover (worker_id, org_path) from tmux when env propagation failed.

    Every QuinnAI worker session is named 'qn-wrkr-XXX' by tmux_spawner and
    has QUINN_ORG_PATH in its session env. When claude's Bash tool spawns
    qn-bd inside the session, the bash subprocess inherits $TMUX, so:
      - 'tmux display-message -p #S' → 'qn-wrkr-XXX' (worker id)
      - 'tmux show-environment QUINN_ORG_PATH' → 'QUINN_ORG_PATH=/path' (org)

    Bullet-proof against env scrubbing through intermediate shells
    (quinn-ai-3gwh).
    """
    if not os.environ.get("TMUX"):
        return None, None
    worker_id: Optional[str] = None
    org_path: Optional[str] = None
    try:
        r = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0:
            m = _TMUX_SESSION_PATTERN.match(r.stdout.strip())
            if m:
                worker_id = m.group(1)
        r = subprocess.run(
            ["tmux", "show-environment", "QUINN_ORG_PATH"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0:
            line = r.stdout.strip()
            if "=" in line:
                key, _, value = line.partition("=")
                if key == "QUINN_ORG_PATH" and value:
                    org_path = value
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return worker_id, org_path


def main():
    """Entry point for qn-bd command.

    Passes all arguments to bd with org context.
    Uses explicit CLI arguments for configuration, with env var fallback.
    """
    import argparse

    # Parse our arguments separately from bd arguments
    parser = argparse.ArgumentParser(
        description="Run beads with org context",
        add_help=False,  # Don't intercept --help, pass to bd
    )
    parser.add_argument(
        "--org-path",
        type=Path,
        default=os.environ.get("QUINN_ORG_PATH"),
        help="Path to org folder. Falls back to $QUINN_ORG_PATH, then to tmux session env.",
    )
    parser.add_argument(
        "--worker-id",
        default=os.environ.get("QUINN_WORKER_ID"),
        help="Worker ID. Falls back to $QUINN_WORKER_ID, then to tmux session name.",
    )

    # Parse known args, pass rest to bd
    our_args, bd_args = parser.parse_known_args()

    # Tmux fallback for both fields when env didn't propagate.
    if our_args.org_path is None or our_args.worker_id is None:
        tmux_worker, tmux_org = _resolve_from_tmux()
        if our_args.worker_id is None and tmux_worker is not None:
            our_args.worker_id = tmux_worker
        if our_args.org_path is None and tmux_org is not None:
            our_args.org_path = Path(tmux_org)

    # Validate org_path
    if not our_args.org_path:
        print(
            "Error: org_path required. Use --org-path, set QUINN_ORG_PATH, "
            "or run inside a tmux session named 'qn-wrkr-XXX' (auto-detected).",
            file=sys.stderr,
        )
        sys.exit(1)

    org_path = Path(our_args.org_path)

    # Pre-pass: evaluate the rules engine on mutating bd verbs before shelling
    # out. Per quinn-ai-t2zb §F.1 and zm8a §6, action names follow the
    # format `qn-bd.<verb>` where verb ∈ {create, update, close, ...}.
    # Read-only verbs (list, show, ready, etc.) are NOT subject to rule eval
    # per t2zb §10 non-goal #9.
    rule_decision_exit = _evaluate_qn_bd_action(
        bd_args=bd_args,
        org_path=org_path,
        worker_id=our_args.worker_id,
    )
    if rule_decision_exit is not None:
        sys.exit(rule_decision_exit)

    # Monorepo per-app .beads routing (quinn-ai-a3pg.1.1): in host mode, a
    # worker invoking qn-bd from inside an app subtree (e.g. apps/raise/) hits
    # that app's own tracker, not the meta-repo .beads. Outside host mode this
    # resolves to the org's .beads (unchanged). cwd is the worker's location.
    from cli.core.bd_wrapper import resolve_beads_dir

    beads_dir = resolve_beads_dir(org_path)

    try:
        result = run_bd(
            args=bd_args,
            org_path=org_path,
            worker_id=our_args.worker_id,
            beads_dir=beads_dir,
        )
        sys.exit(result.returncode)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except BeadPermissionError as e:
        print(f"Permission denied: {e}", file=sys.stderr)
        sys.exit(1)
    except LifecycleError as e:
        print(f"Lifecycle error: {e}", file=sys.stderr)
        sys.exit(1)


_MUTATING_BD_VERBS = frozenset({"create", "update", "close", "comment"})
_BD_TEXT_FLAGS = ("--title", "--description", "--notes", "--design", "--reason", "--body", "-t", "-d")


def _evaluate_qn_bd_action(
    *,
    bd_args: list[str],
    org_path: Path,
    worker_id: Optional[str],
) -> Optional[int]:
    """Evaluate the rules engine on the qn-bd invocation.

    Returns:
        None if rules allow the action (or it's read-only / no rules apply).
        An exit code (1) if the action is blocked by a rule.
    """
    # Find the verb (first non-flag token).
    verb: Optional[str] = None
    for token in bd_args:
        if not token.startswith("-"):
            verb = token
            break

    if verb is None or verb not in _MUTATING_BD_VERBS:
        return None

    # Extract free-text body from --description / --notes / --title / etc.
    body_parts: list[str] = []
    skip_next = False
    for i, token in enumerate(bd_args):
        if skip_next:
            skip_next = False
            continue
        for flag in _BD_TEXT_FLAGS:
            if token == flag:
                if i + 1 < len(bd_args):
                    body_parts.append(bd_args[i + 1])
                skip_next = True
                break
            if token.startswith(f"{flag}="):
                body_parts.append(token.split("=", 1)[1])
                break
    body = " ".join(body_parts)

    # Lazy import to avoid cycles and keep startup cost low for read-only paths.
    try:
        from cli.core.db import open_database, get_org_db_path
        from cli.core.rules.audit import AuditLogger
        from cli.core.rules.engine import RuleEngine
        from cli.core.rules.loader import load_rules
        from cli.core.rules.types import DecisionKind
    except ImportError:
        return None

    if os.environ.get("QUINNAI_RULES_DISABLED") == "1":
        from cli.core.rules._disabled import DisabledRuleEngine

        audit = AuditLogger(org_path / "live" / "rules-audit.jsonl")
        engine = DisabledRuleEngine(audit)
    else:
        try:
            ruleset = load_rules(org_path)
        except Exception:
            # Fail closed (per t2zb §10 non-goal #10): if rules can't load,
            # refuse the action.
            print("Error: rules engine failed to load — action refused.", file=sys.stderr)
            return 1
        try:
            db = open_database(get_org_db_path(org_path))
        except Exception:
            db = None
        audit = AuditLogger(org_path / "live" / "rules-audit.jsonl")
        engine = RuleEngine(ruleset, db, audit)

    # Extract and STRIP --justify and --override flags before passing to bd.
    # These are QuinnAI-only flags for the rules engine; bd doesn't know them.
    justify_bead_id: Optional[str] = None
    override_bead_id: Optional[str] = None
    stripped_args: list[str] = []
    i = 0
    while i < len(bd_args):
        tok = bd_args[i]
        if tok == "--justify" and i + 1 < len(bd_args):
            justify_bead_id = bd_args[i + 1]
            i += 2
            continue
        if tok.startswith("--justify="):
            justify_bead_id = tok.split("=", 1)[1]
            i += 1
            continue
        if tok == "--override" and i + 1 < len(bd_args):
            override_bead_id = bd_args[i + 1]
            i += 2
            continue
        if tok.startswith("--override="):
            override_bead_id = tok.split("=", 1)[1]
            i += 1
            continue
        stripped_args.append(tok)
        i += 1
    bd_args[:] = stripped_args

    action = f"qn-bd.{verb}"
    context = {
        "worker_id": worker_id,
        "worker_role": None,
        "worker_role_level": None,
        "env": "dev",
        "args": {},
        "body": body,
        "target_paths": [],
        "command": " ".join(bd_args),
    }

    decision = engine.evaluate(action, context, justify_bead_id=justify_bead_id, override_bead_id=override_bead_id)

    if decision.kind == DecisionKind.ALLOW:
        return None
    if decision.kind == DecisionKind.ALLOW_WITH_NUDGE:
        print(decision.message, file=sys.stderr)
        return None

    msg = decision.message
    if decision.remediation:
        msg = f"{msg}\n{decision.remediation}"
    print(msg, file=sys.stderr)
    return 1

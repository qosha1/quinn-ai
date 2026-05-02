"""qn-tool-guard — Claude Code PreToolUse hook that enforces board rules.

Called by Claude Code before every tool use. Reads JSON from stdin in the
Claude Code hook protocol format, evaluates against the rule engine, and
exits 0 (allow) or 1 (block, with message on stdout for the model to see).

Protocol (Claude Code hook stdin):
    {"tool_name": "Bash", "tool_input": {"command": "..."}}

Exit codes:
    0 — allow
    1 — block (stdout message shown to model)
    2 — rules engine error (fail-open: allow + log warning)
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Public API (used by tests)
# ---------------------------------------------------------------------------

@dataclass
class GuardResult:
    allowed: bool
    rule_id: Optional[str]
    message: Optional[str]


def evaluate_tool_call(
    *,
    tool_name: str,
    tool_input: dict,
    org_path: Path,
    worker_id: Optional[str],
) -> GuardResult:
    """Evaluate a tool call against the rule engine.

    Maps the tool call to a rule action and body, then asks the engine.
    Returns GuardResult(allowed=True) for unknown tools or read-only ops.
    """
    action, body = _extract_action_and_body(tool_name, tool_input)
    if action is None:
        return GuardResult(allowed=True, rule_id=None, message=None)

    try:
        from cli.core.rules.loader import load_rules
        from cli.core.rules.engine import RuleEngine
        from cli.core.rules.audit import AuditLogger
        from cli.core.rules.types import DecisionKind

        ruleset = load_rules(org_path)
        audit = AuditLogger(org_path / "live" / "rules-audit.jsonl")
        engine = RuleEngine(ruleset, db=None, audit_logger=audit)

        context = {
            "worker_id": worker_id,
            "worker_role": None,
            "worker_role_level": None,
            "env": os.environ.get("QUINN_ENV", "dev"),
            "args": {},
            "body": body,
            "target_paths": _extract_target_paths(tool_name, tool_input),
            "command": body,
        }
        decision = engine.evaluate(action, context)

        if decision.kind == DecisionKind.ALLOW or decision.kind == DecisionKind.ALLOW_WITH_NUDGE:
            return GuardResult(allowed=True, rule_id=None, message=decision.message)

        rule_id = decision.rule.id if decision.rule else "unknown"
        msg = decision.message or f"Blocked by rule: {rule_id}"
        if decision.remediation:
            msg = f"{msg}\n{decision.remediation}"
        return GuardResult(allowed=False, rule_id=rule_id, message=msg)

    except Exception as e:
        # Fail open on engine errors — log warning but don't block work
        print(f"[qn-tool-guard] warning: rules engine error ({e}), allowing", file=sys.stderr)
        return GuardResult(allowed=True, rule_id=None, message=None)


def _extract_action_and_body(tool_name: str, tool_input: dict) -> tuple[Optional[str], str]:
    """Map a Claude Code tool name + input to a (rule_action, body) pair."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return "shell.bash", cmd

    if tool_name in ("Write", "NotebookEdit"):
        path = tool_input.get("file_path", tool_input.get("notebook_path", ""))
        content = tool_input.get("content", tool_input.get("new_source", ""))
        return "session.write", f"{path} {content}"

    if tool_name == "Edit":
        path = tool_input.get("file_path", "")
        new_str = tool_input.get("new_string", "")
        return "session.edit", f"{path} {new_str}"

    # Read-only tools (Read, Glob, Grep, WebFetch, WebSearch, etc.) — no rule check
    return None, ""


def _extract_target_paths(tool_name: str, tool_input: dict) -> list[str]:
    if tool_name in ("Write", "Edit", "Read"):
        p = tool_input.get("file_path")
        return [p] if p else []
    return []


# ---------------------------------------------------------------------------
# CLI entry point (called by Claude Code hook)
# ---------------------------------------------------------------------------

def tool_guard_main() -> None:
    """Entry point: read hook JSON from stdin, evaluate, exit 0/1."""
    org_path_str = os.environ.get("QUINN_ORG_PATH") or os.environ.get("ORG_PATH")
    worker_id = os.environ.get("QUINN_WORKER_ID") or os.environ.get("WORKER_ID")

    if not org_path_str:
        # No org context — cannot evaluate, fail open
        sys.exit(0)

    org_path = Path(org_path_str)

    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        payload = json.loads(raw)
    except Exception:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    result = evaluate_tool_call(
        tool_name=tool_name,
        tool_input=tool_input,
        org_path=org_path,
        worker_id=worker_id,
    )

    if result.allowed:
        sys.exit(0)
    else:
        print(result.message or f"Blocked by board rule: {result.rule_id}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    tool_guard_main()

"""RuleEngine — evaluates worker actions against a loaded RuleSet.

Per quinn-ai-t2zb §C, quinn-ai-zm8a §3, quinn-ai-p286 §1.

Severity behavior (per c5hb §1, t2zb §B):
- SUGGESTED: matched -> ALLOW_WITH_NUDGE; unmatched action -> ALLOW.
- ENCOURAGED: matched -> REQUIRES_JUSTIFY (no --justify), ALLOW (valid justify
  bead: worker-owned, non-empty body), BLOCK (bad/missing justify bead).
- REQUIRED: matched -> REQUIRES_OVERRIDE (no --override), ALLOW (valid override:
  status=approved AND approver_id == worker's direct manager), BLOCK (bad override).
- ABSOLUTE: matched -> BLOCK unconditionally; --justify and --override ignored.

The engine stops at the first matching rule (rules are pre-sorted by id at load
time for determinism). Multiple rules per action across overlapping scopes is
operator error; layer via `scope` to disambiguate.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from cli.core.rules.types import (
    Decision,
    DecisionKind,
    Rule,
    RuleSet,
    Severity,
)


class RuleEngine:
    """Evaluates actions against a RuleSet."""

    def __init__(self, ruleset: RuleSet, db: Any, audit_logger: Any) -> None:
        self.ruleset = ruleset
        self.db = db
        self.audit = audit_logger
        # Pre-index rules by action for fast lookup.
        self._rules_by_action: dict[str, tuple[Rule, ...]] = {}
        for rule in ruleset.rules:
            for action in rule.actions:
                existing = self._rules_by_action.get(action, ())
                self._rules_by_action[action] = existing + (rule,)
        # Side-cache for rules constructed programmatically (i.e. in tests where
        # the loader hasn't pre-compiled patterns).
        self._inline_compiled: dict[str, re.Pattern[str]] = {}

    # ---------------------------------------------------------------- public

    def evaluate(
        self,
        action: str,
        context: dict[str, Any],
        *,
        justify_bead_id: Optional[str] = None,
        override_bead_id: Optional[str] = None,
    ) -> Decision:
        """Evaluate the action. Returns a Decision; never raises on rule miss.

        See module docstring for severity behavior.
        """
        candidates = self._rules_by_action.get(action, ())
        matched = self._first_match(candidates, context)

        if matched is None:
            decision = Decision(
                kind=DecisionKind.ALLOW,
                rule=None,
                message="",
            )
            # No-match cases still emit an audit line per t2zb §E.
            self._audit(action, context, decision, justify_bead_id, override_bead_id)
            return decision

        decision = self._apply_severity(
            matched,
            context,
            justify_bead_id=justify_bead_id,
            override_bead_id=override_bead_id,
        )
        self._audit(action, context, decision, justify_bead_id, override_bead_id)
        return decision

    # --------------------------------------------------------------- private

    def _first_match(
        self, candidates: tuple[Rule, ...], context: dict[str, Any]
    ) -> Optional[Rule]:
        for rule in candidates:
            if not self._scope_matches(rule, context):
                continue
            if not self._pattern_matches(rule, context):
                continue
            return rule
        return None

    def _scope_matches(self, rule: Rule, context: dict[str, Any]) -> bool:
        if rule.scope is None:
            return True
        scope = rule.scope
        if scope.env is not None and context.get("env") != scope.env:
            return False
        if scope.worker_role is not None and context.get("worker_role") != scope.worker_role:
            return False
        if scope.worker_role_min_level is not None:
            level = context.get("worker_role_level")
            if level is None or level < scope.worker_role_min_level:
                return False
        if scope.target_path_prefix is not None:
            target_paths = context.get("target_paths", []) or []
            if not any(str(p).startswith(scope.target_path_prefix) for p in target_paths):
                return False
        return True

    def _pattern_matches(self, rule: Rule, context: dict[str, Any]) -> bool:
        if rule.pattern is None:
            return True

        target_value = self._resolve_pattern_target(rule.pattern.target, context)
        if target_value is None:
            return False

        if rule.pattern.kind == "regex":
            compiled = self._get_compiled_regex(rule)
            if compiled is None:
                return False
            return compiled.search(str(target_value)) is not None
        if rule.pattern.kind == "contains":
            return rule.pattern.expr in str(target_value)
        if rule.pattern.kind == "glob":
            from fnmatch import fnmatch
            return fnmatch(str(target_value), rule.pattern.expr)
        return False

    @staticmethod
    def _resolve_pattern_target(target: str, context: dict[str, Any]) -> Any:
        if target == "body":
            return context.get("body")
        if target == "command":
            return context.get("command")
        if target == "path":
            paths = context.get("target_paths", []) or []
            return paths[0] if paths else None
        if target.startswith("argument:"):
            arg_name = target.split(":", 1)[1]
            return (context.get("args") or {}).get(arg_name)
        return None

    def _get_compiled_regex(self, rule: Rule) -> Optional[re.Pattern[str]]:
        # Try the loader's side-cache first.
        from cli.core.rules.loader import get_compiled_pattern

        cached = get_compiled_pattern(rule.id)
        if cached is not None:
            return cached
        # Fall back to inline compile (programmatic Rule construction, e.g. in tests).
        if rule.id in self._inline_compiled:
            return self._inline_compiled[rule.id]
        try:
            compiled = re.compile(rule.pattern.expr)  # type: ignore[union-attr]
        except re.error:
            return None
        self._inline_compiled[rule.id] = compiled
        return compiled

    def _apply_severity(
        self,
        rule: Rule,
        context: dict[str, Any],
        *,
        justify_bead_id: Optional[str],
        override_bead_id: Optional[str],
    ) -> Decision:
        if rule.severity == Severity.ABSOLUTE:
            return Decision(
                kind=DecisionKind.BLOCK,
                rule=rule,
                message=f"Action refused by ABSOLUTE rule '{rule.id}': {rule.description}",
                remediation="ABSOLUTE rules can only be removed by editing rules.yaml and restarting the org.",
            )

        if rule.severity == Severity.SUGGESTED:
            return Decision(
                kind=DecisionKind.ALLOW_WITH_NUDGE,
                rule=rule,
                message=f"[rule '{rule.id}'] {rule.description}",
                remediation="",
            )

        if rule.severity == Severity.ENCOURAGED:
            if justify_bead_id is None:
                return Decision(
                    kind=DecisionKind.REQUIRES_JUSTIFY,
                    rule=rule,
                    message=f"Rule '{rule.id}' requires --justify <bead-id>: {rule.description}",
                    remediation=(
                        "File a bead with the supporting artifact (test results, "
                        "report, data) and re-invoke with --justify <bead-id>."
                    ),
                )
            if not self._justify_is_valid(context, justify_bead_id):
                return Decision(
                    kind=DecisionKind.BLOCK,
                    rule=rule,
                    message=(
                        f"Rule '{rule.id}': --justify bead is missing, "
                        f"not owned by you, or has empty body."
                    ),
                    remediation="File a worker-owned bead with non-empty body and retry.",
                )
            return Decision(
                kind=DecisionKind.ALLOW,
                rule=rule,
                message=f"[rule '{rule.id}'] justified by {justify_bead_id}",
            )

        if rule.severity == Severity.REQUIRED:
            if override_bead_id is None:
                return Decision(
                    kind=DecisionKind.REQUIRES_OVERRIDE,
                    rule=rule,
                    message=f"Rule '{rule.id}' requires --override <bead-id>: {rule.description}",
                    remediation=(
                        "File an override-request bead, have your direct manager "
                        "set status=approved, then re-invoke with --override <bead-id>."
                    ),
                )
            if not self._override_is_valid(context, override_bead_id):
                return Decision(
                    kind=DecisionKind.BLOCK,
                    rule=rule,
                    message=(
                        f"Rule '{rule.id}': --override bead is missing, not approved, "
                        f"or not approved by your direct manager."
                    ),
                    remediation=(
                        "Override beads must have status=approved AND approver_id "
                        "matching your direct manager."
                    ),
                )
            return Decision(
                kind=DecisionKind.ALLOW,
                rule=rule,
                message=f"[rule '{rule.id}'] overridden by {override_bead_id}",
            )

        # Should never happen — Severity is a closed enum.
        return Decision(kind=DecisionKind.BLOCK, rule=rule, message="unknown severity")

    def _justify_is_valid(self, context: dict[str, Any], bead_id: str) -> bool:
        bead = self.db.get_bead(bead_id)
        if bead is None:
            return False
        worker_id = context.get("worker_id")
        if bead.get("owner") != worker_id:
            return False
        body = bead.get("body") or ""
        return len(body.strip()) > 0

    def _override_is_valid(self, context: dict[str, Any], bead_id: str) -> bool:
        bead = self.db.get_bead(bead_id)
        if bead is None:
            return False
        if bead.get("status") != "approved":
            return False
        worker_id = context.get("worker_id")
        manager_id = self.db.get_direct_manager(worker_id)
        if manager_id is None:
            return False
        return bead.get("approver_id") == manager_id

    def _audit(
        self,
        action: str,
        context: dict[str, Any],
        decision: Decision,
        justify_bead_id: Optional[str],
        override_bead_id: Optional[str],
    ) -> None:
        self.audit.record(
            worker_id=context.get("worker_id"),
            action=action,
            rule_id=decision.rule.id if decision.rule is not None else None,
            decision=decision.kind,
            justify_bead=justify_bead_id,
            override_bead=override_bead_id,
            context_summary={
                "env": context.get("env"),
                "worker_role": context.get("worker_role"),
            },
        )

"""DisabledRuleEngine — kill-switch implementation that always allows.

Per quinn-ai-p286 §4 + zm8a §3: when QUINNAI_RULES_DISABLED=1 is set, the
Context swaps the real RuleEngine for this strategy-pattern alternative.
Branch-free hot path; every evaluation is audited with kill_switch_used=true
so post-mortem investigators can find emergency-use windows.
"""

from __future__ import annotations

from typing import Any, Optional

from cli.core.rules.types import Decision, DecisionKind


class DisabledRuleEngine:
    """RuleEngine-compatible interface that always returns ALLOW.

    Same shape as RuleEngine.evaluate() so callers don't need to branch.
    Audit logs each call with kill_switch_used=true.
    """

    def __init__(self, audit_logger: Any) -> None:
        self.audit = audit_logger
        # No db / ruleset needed — we always allow.
        self.db = None
        self.ruleset = None

    def evaluate(
        self,
        action: str,
        context: dict[str, Any],
        *,
        justify_bead_id: Optional[str] = None,
        override_bead_id: Optional[str] = None,
    ) -> Decision:
        decision = Decision(
            kind=DecisionKind.ALLOW,
            rule=None,
            message="rules engine disabled via QUINNAI_RULES_DISABLED",
        )
        self.audit.record(
            worker_id=context.get("worker_id"),
            action=action,
            rule_id=None,
            decision=decision.kind,
            justify_bead=justify_bead_id,
            override_bead=override_bead_id,
            context_summary={
                "env": context.get("env"),
                "worker_role": context.get("worker_role"),
            },
            kill_switch_used=True,
        )
        return decision

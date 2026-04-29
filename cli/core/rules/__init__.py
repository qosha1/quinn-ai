"""Board rules engine — graded-severity action gating for worker mutations.

Public surface (per zm8a §2):
- Enums: Severity, DecisionKind
- Dataclasses: Rule, RuleSet, Pattern, Scope, Decision
- (Forthcoming) Engine: RuleEngine, evaluate_or_raise
- (Forthcoming) Decorator: requires_rule_check
- (Forthcoming) Logger: AuditLogger
"""

from cli.core.rules.types import (
    Decision,
    DecisionKind,
    Pattern,
    Rule,
    RuleSet,
    Scope,
    Severity,
)

__all__ = [
    "Decision",
    "DecisionKind",
    "Pattern",
    "Rule",
    "RuleSet",
    "Scope",
    "Severity",
]

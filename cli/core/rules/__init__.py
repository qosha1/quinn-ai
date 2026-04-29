"""Board rules engine — graded-severity action gating for worker mutations.

Public surface (per zm8a §2):
- Enums: Severity, DecisionKind
- Dataclasses: Rule, RuleSet, Pattern, Scope, Decision
- (Forthcoming) Engine: RuleEngine, evaluate_or_raise
- (Forthcoming) Decorator: requires_rule_check
- (Forthcoming) Logger: AuditLogger
"""

from cli.core.rules.audit import AuditLogger
from cli.core.rules.decorators import evaluate_or_raise, requires_rule_check
from cli.core.rules.engine import RuleEngine
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
    "AuditLogger",
    "Decision",
    "DecisionKind",
    "Pattern",
    "Rule",
    "RuleEngine",
    "RuleSet",
    "Scope",
    "Severity",
    "evaluate_or_raise",
    "requires_rule_check",
]

"""Context object for msgr commands."""

from pathlib import Path
from typing import Optional

import click

from cli.core.db import Database, get_org_db_path


class MsgrContext:
    """Context object for msgr commands.

    Provides database connection and worker identity to commands.
    """

    def __init__(self, org_path: Path, worker_id: Optional[str] = None):
        self.org_path = org_path
        self.worker_id = worker_id
        self._db: Optional[Database] = None
        self._rules = None
        self._rules_audit = None

    @property
    def db(self) -> Database:
        """Get database connection (lazy init)."""
        if self._db is None:
            self._db = Database(str(get_org_db_path(self.org_path)))
        return self._db

    @property
    def rules_audit(self):
        """Rules-engine audit logger (lazy load)."""
        if self._rules_audit is None:
            from cli.core.rules.audit import AuditLogger

            self._rules_audit = AuditLogger(self.org_path / "live" / "rules-audit.jsonl")
        return self._rules_audit

    @property
    def rules(self):
        """Rules engine (lazy load)."""
        if self._rules is None:
            import os
            from cli.core.rules.engine import RuleEngine
            from cli.core.rules.loader import load_rules

            if os.environ.get("QUINNAI_RULES_DISABLED") == "1":
                from cli.core.rules._disabled import DisabledRuleEngine

                self._rules = DisabledRuleEngine(self.rules_audit)
            else:
                ruleset = load_rules(self.org_path)
                self._rules = RuleEngine(ruleset, self.db, self.rules_audit)
        return self._rules

    def close(self):
        """Close database connection."""
        if self._db is not None:
            self._db.close()
            self._db = None


# Pass context decorator
pass_context = click.make_pass_decorator(MsgrContext)

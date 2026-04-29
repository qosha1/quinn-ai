"""
CLI context shared across all commands.

Follows "No Config Discovery" principle - all values are passed explicitly
through CLI options, which may use envvar as a convenience but the flow
is still explicit (CLI option -> Context -> command).
"""

from pathlib import Path
from typing import Optional, TYPE_CHECKING

import click

from cli.core.db import open_database, get_org_db_path
from cli.core.config import (
    OrgConfig,
    load_org_config,
    get_org_config_path,
    validate_org_config,
    warn_plaintext_api_keys,
)
from shared.exceptions import ConfigurationError

if TYPE_CHECKING:
    from cli.core.context import OrgContext


class Context:
    """CLI context holding shared state.

    Values are set from CLI options (which may use envvar), not from
    direct environment variable reads in command implementations.

    Provides lazy-loaded access to:
    - db: Database connection
    - config: Organization configuration (with validation)
    - org_context: Full OrgContext for services (budget, bead, storage)
    """

    def __init__(
        self,
        org_path: Optional[Path] = None,
        worker_id: Optional[str] = None,
    ):
        self.org_path = org_path
        self.worker_id = worker_id
        self._db = None
        self._config: Optional[OrgConfig] = None
        self._org_context: Optional["OrgContext"] = None
        self._config_validated = False
        self._rules = None
        self._rules_audit = None

    def _require_org_path(self) -> Path:
        """Ensure org_path is set or raise ClickException."""
        if self.org_path is None:
            raise click.ClickException(
                "No org path specified.\n"
                "Use --org-path or set QUINN_ORG_PATH environment variable."
            )
        return self.org_path

    @property
    def db(self):
        """Get database connection (lazy load)."""
        if self._db is None:
            org_path = self._require_org_path()
            db_path = get_org_db_path(org_path)
            if not db_path.exists():
                raise click.ClickException(
                    f"Organization not initialized at '{org_path}'.\n"
                    "Run 'qn org init' to initialize the organization."
                )
            self._db = open_database(db_path)
        return self._db

    @property
    def config(self) -> OrgConfig:
        """Get organization configuration (lazy load with validation).

        Loads config from org_path/config/ directory.
        Validates on first access and warns about plaintext API keys.

        Returns:
            OrgConfig instance

        Raises:
            click.ClickException: If config is missing or invalid
        """
        if self._config is None:
            org_path = self._require_org_path()
            config_path = get_org_config_path(org_path)

            if not config_path.exists():
                raise click.ClickException(
                    f"Configuration not found at '{config_path}'.\n"
                    "Run 'qn org init' to initialize the organization."
                )

            try:
                self._config = load_org_config(config_path)
            except FileNotFoundError as e:
                raise click.ClickException(
                    f"Configuration file missing: {e}\n"
                    "Run 'qn org init' to create default configuration."
                )
            except ValueError as e:
                raise click.ClickException(f"Invalid configuration: {e}")

            # Validate on first load
            if not self._config_validated:
                self._validate_config()
                self._config_validated = True

        return self._config

    def _validate_config(self) -> None:
        """Validate configuration and warn about issues.

        Raises click.ClickException on validation errors.
        Warns about plaintext API keys.
        """
        if self._config is None:
            return

        # Check for plaintext API keys (warning only)
        config_path = get_org_config_path(self._require_org_path())
        providers_path = config_path / "providers.yaml"
        warn_plaintext_api_keys(providers_path)

        # Validate configuration
        errors = validate_org_config(self._config)
        if errors:
            # Format errors for display
            error_msgs = []
            for err in errors:
                if err.provider:
                    error_msgs.append(f"  [{err.provider}] {err}")
                else:
                    error_msgs.append(f"  {err}")

            raise click.ClickException(
                "Configuration validation failed:\n" + "\n".join(error_msgs)
            )

    @property
    def org_context(self) -> "OrgContext":
        """Get full OrgContext for service access (lazy load).

        Provides access to budget_service, bead_service, storage, etc.
        Use this when you need the full service layer, not just db/config.

        Returns:
            OrgContext instance

        Raises:
            click.ClickException: If org not initialized
        """
        if self._org_context is None:
            from cli.core.context import OrgContext, OrgNotFoundError

            org_path = self._require_org_path()
            try:
                self._org_context = OrgContext.create(org_path)
            except OrgNotFoundError:
                raise click.ClickException(
                    f"Organization not initialized at '{org_path}'.\n"
                    "Run 'qn org init' to initialize the organization."
                )

        return self._org_context

    @property
    def rules_audit(self):
        """Get the rules-engine audit logger (lazy load).

        Writes JSONL one-line-per-evaluation to org/live/rules-audit.jsonl
        per quinn-ai-t2zb §E.
        """
        if self._rules_audit is None:
            from cli.core.rules.audit import AuditLogger

            org_path = self._require_org_path()
            audit_path = org_path / "live" / "rules-audit.jsonl"
            self._rules_audit = AuditLogger(audit_path)
        return self._rules_audit

    @property
    def rules(self):
        """Get the rules engine (lazy load).

        Loads org/config/rules.yaml (or default catalog if absent) and wires up
        the RuleEngine with this Context's db + audit logger. Per quinn-ai-p286
        §4 the kill-switch QUINNAI_RULES_DISABLED=1 swaps in a permissive engine.
        """
        if self._rules is None:
            import os
            from cli.core.rules.engine import RuleEngine
            from cli.core.rules.loader import load_rules

            org_path = self._require_org_path()

            if os.environ.get("QUINNAI_RULES_DISABLED") == "1":
                from cli.core.rules._disabled import DisabledRuleEngine

                self._rules = DisabledRuleEngine(self.rules_audit)
            else:
                ruleset = load_rules(org_path)
                self._rules = RuleEngine(ruleset, self.db, self.rules_audit)
        return self._rules

    def close(self):
        """Close database connection and org context."""
        if self._db is not None:
            self._db.close()
            self._db = None
        if self._org_context is not None:
            self._org_context.close()
            self._org_context = None


pass_context = click.make_pass_decorator(Context, ensure=True)

"""qn org rules — CLI surface for the board-rules engine.

Per quinn-ai-zm8a §1, this module owns the operator-facing subcommand group:
    qn org rules list                 — table of all rules from the loaded RuleSet
    qn org rules show <rule-id>       — print one rule's full definition
    qn org rules validate             — load org/config/rules.yaml; non-zero on schema fail
    qn org rules test <action> ...    — dry-run the engine, print the Decision
    qn org rules disable <rule-id>    — comment out a rule in rules.yaml (in-place)
    qn org rules add                  — interactive scaffold; appends a new rule to rules.yaml

The group is constructed here and registered into `qn org` from
`cli/commands/org/__init__.py`. All commands operate on the org rooted at
`ctx.org_path` (Click context) and never reach outside that scope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from cli.commands.context import Context, pass_context
from cli.core.rules.audit import AuditLogger
from cli.core.rules.engine import RuleEngine
from cli.core.rules.loader import load_rules
from cli.core.rules.types import Severity
from shared.exceptions import RuleSetLoadError


# Severity values valid for `qn org rules add` interactive prompt and for
# `disable` / `test` rendering. Source: shared/state_machines.py is for
# state transitions; rule severities live in cli.core.rules.types.Severity.
_VALID_SEVERITIES = tuple(s.value for s in Severity)


@click.group("rules")
def rules_cmd() -> None:
    """Manage the org's board rules.

    Rules are graded-severity gates (SUGGESTED / ENCOURAGED / REQUIRED /
    ABSOLUTE) that the engine consults before mutating actions. They live in
    `<org>/config/rules.yaml`; falling back to the bundled default catalog if
    the file is absent.
    """
    pass


# ---------------------------------------------------------------------------
# qn org rules list
# ---------------------------------------------------------------------------


@rules_cmd.command("list")
@pass_context
def list_cmd(ctx: Context) -> None:
    """List active rules in the loaded RuleSet.

    Columns: id, severity, actions, description (truncated).
    """
    org_path = ctx.org_path
    if org_path is None:
        raise click.ClickException(
            "No org path specified.\n"
            "Use --org-path or set QUINN_ORG_PATH."
        )

    try:
        ruleset = load_rules(org_path)
    except RuleSetLoadError as exc:
        raise click.ClickException(str(exc))

    if not ruleset.rules:
        click.echo("(no rules)")
        return

    # Compute column widths off the actual content so the table fits the data.
    id_w = max(len("id"), *(len(r.id) for r in ruleset.rules))
    sev_w = max(len("severity"), *(len(r.severity.value) for r in ruleset.rules))
    actions_strs = [", ".join(r.actions) for r in ruleset.rules]
    actions_w = max(len("actions"), *(len(s) for s in actions_strs))

    desc_truncate_to = 60

    header = f"{'id'.ljust(id_w)}  {'severity'.ljust(sev_w)}  {'actions'.ljust(actions_w)}  description"
    click.echo(header)
    click.echo("-" * len(header))
    for rule, actions_str in zip(ruleset.rules, actions_strs):
        desc = rule.description
        if len(desc) > desc_truncate_to:
            desc = desc[: desc_truncate_to - 1] + "…"
        click.echo(
            f"{rule.id.ljust(id_w)}  "
            f"{rule.severity.value.ljust(sev_w)}  "
            f"{actions_str.ljust(actions_w)}  "
            f"{desc}"
        )


# ---------------------------------------------------------------------------
# qn org rules show <rule-id>
# ---------------------------------------------------------------------------


@rules_cmd.command("show")
@click.argument("rule_id")
@pass_context
def show_cmd(ctx: Context, rule_id: str) -> None:
    """Print the full definition of one rule."""
    org_path = ctx.org_path
    if org_path is None:
        raise click.ClickException(
            "No org path specified.\n"
            "Use --org-path or set QUINN_ORG_PATH."
        )

    try:
        ruleset = load_rules(org_path)
    except RuleSetLoadError as exc:
        raise click.ClickException(str(exc))

    matches = [r for r in ruleset.rules if r.id == rule_id]
    if not matches:
        raise click.ClickException(f"rule '{rule_id}' not found")

    rule = matches[0]
    click.echo(f"id:          {rule.id}")
    click.echo(f"severity:    {rule.severity.value}")
    click.echo(f"actions:     {', '.join(rule.actions)}")
    click.echo(f"description: {rule.description}")
    if rule.pattern is not None:
        click.echo("pattern:")
        click.echo(f"  kind:   {rule.pattern.kind}")
        click.echo(f"  target: {rule.pattern.target}")
        click.echo(f"  expr:   {rule.pattern.expr}")
    if rule.scope is not None:
        click.echo("scope:")
        if rule.scope.env is not None:
            click.echo(f"  env:                   {rule.scope.env}")
        if rule.scope.worker_role is not None:
            click.echo(f"  worker_role:           {rule.scope.worker_role}")
        if rule.scope.worker_role_min_level is not None:
            click.echo(f"  worker_role_min_level: {rule.scope.worker_role_min_level}")
        if rule.scope.target_path_prefix is not None:
            click.echo(f"  target_path_prefix:    {rule.scope.target_path_prefix}")
    if rule.artifact_required:
        click.echo("artifact_required: true")
    if rule.notes:
        click.echo(f"notes: {rule.notes}")


# ---------------------------------------------------------------------------
# qn org rules validate
# ---------------------------------------------------------------------------


@rules_cmd.command("validate")
@pass_context
def validate_cmd(ctx: Context) -> None:
    """Validate the org's rules.yaml. Non-zero exit on schema failure."""
    org_path = ctx.org_path
    if org_path is None:
        raise click.ClickException(
            "No org path specified.\n"
            "Use --org-path or set QUINN_ORG_PATH."
        )

    try:
        ruleset = load_rules(org_path)
    except RuleSetLoadError as exc:
        # ClickException prints to stderr and exits 1.
        raise click.ClickException(str(exc))

    click.echo(f"OK: {len(ruleset.rules)} rule(s) loaded from {ruleset.source_path}")


# ---------------------------------------------------------------------------
# qn org rules test <action> [--justify ...] [--override ...] [--worker-id ...]
# ---------------------------------------------------------------------------


@rules_cmd.command("test")
@click.argument("action")
@click.option(
    "--justify",
    "justify_bead",
    type=str,
    default=None,
    help="Bead id to pass as --justify (ENCOURAGED rules).",
)
@click.option(
    "--override",
    "override_bead",
    type=str,
    default=None,
    help="Bead id to pass as --override (REQUIRED rules).",
)
@click.option(
    "--worker-id",
    "worker_id",
    type=str,
    default=None,
    help="Synthetic worker id to put in the action context.",
)
@click.option(
    "--env",
    "env",
    type=str,
    default=None,
    help="Synthetic environment string (matches scope.env).",
)
@click.option(
    "--body",
    "body",
    type=str,
    default=None,
    help="Synthetic action body text (matches pattern target=body).",
)
@pass_context
def test_cmd(
    ctx: Context,
    action: str,
    justify_bead: Optional[str],
    override_bead: Optional[str],
    worker_id: Optional[str],
    env: Optional[str],
    body: Optional[str],
) -> None:
    """Dry-run the rules engine against a synthetic action context.

    Builds a context dict from the flags and prints the resulting Decision
    (kind + matched rule id + message). No audit log is written to disk;
    a no-op AuditLogger backed by a temp file is used so the engine's
    internal contract (audit on every eval) is honored.
    """
    org_path = ctx.org_path
    if org_path is None:
        raise click.ClickException(
            "No org path specified.\n"
            "Use --org-path or set QUINN_ORG_PATH."
        )

    try:
        ruleset = load_rules(org_path)
    except RuleSetLoadError as exc:
        raise click.ClickException(str(exc))

    # Test command is a dry run: write audit to a discardable path under
    # /tmp via tempfile so we don't pollute org/live/.
    import tempfile

    tmp_audit = Path(tempfile.mkstemp(prefix="qn-rules-test-", suffix=".jsonl")[1])
    audit = AuditLogger(tmp_audit)
    # The engine's justify/override-validation paths call db.get_bead /
    # db.get_direct_manager. For a synthetic test we always treat the bead
    # check as failed unless the test invocation gave us a real db. The
    # operator can extend this later — for now a thin stub keeps the
    # subcommand decoupled from sqlite.
    engine = RuleEngine(ruleset, db=_DryRunDB(), audit_logger=audit)

    context_dict: dict = {
        "worker_id": worker_id,
        "env": env,
        "body": body,
    }

    decision = engine.evaluate(
        action,
        context_dict,
        justify_bead_id=justify_bead,
        override_bead_id=override_bead,
    )

    rule_id = decision.rule.id if decision.rule is not None else "<no-match>"
    click.echo(f"decision: {decision.kind.value}")
    click.echo(f"rule:     {rule_id}")
    if decision.message:
        click.echo(f"message:  {decision.message}")
    if decision.remediation:
        click.echo(f"remediation: {decision.remediation}")


class _DryRunDB:
    """Minimal stand-in DB used by `qn org rules test`.

    The real engine wants `get_bead(bead_id)` and `get_direct_manager(worker_id)`
    when validating --justify / --override flags. Test-mode cannot reach
    real beads, so this returns "no such bead" and "no manager" — meaning
    any --justify / --override the operator passes will be flagged as
    invalid by the engine and BLOCK out (which is the right behavior:
    test mode is a dry run that says "what WOULD happen", not "what
    succeeds in production").
    """

    def get_bead(self, bead_id: str) -> dict | None:  # noqa: ARG002 - intentional stub
        return None

    def get_direct_manager(self, worker_id: str | None) -> str | None:  # noqa: ARG002
        return None


# ---------------------------------------------------------------------------
# qn org rules disable <rule-id>
# ---------------------------------------------------------------------------


@rules_cmd.command("disable")
@click.argument("rule_id")
@pass_context
def disable_cmd(ctx: Context, rule_id: str) -> None:
    """Comment out a rule in rules.yaml (in-place; non-destructive).

    The block is kept in the file (each line prefixed with `#`) so the
    operator can restore it by hand. If the rule isn't in the file, exit
    non-zero — falling back to the bundled default catalog wouldn't help
    here (we can't comment out a file that doesn't exist).
    """
    org_path = ctx.org_path
    if org_path is None:
        raise click.ClickException(
            "No org path specified.\n"
            "Use --org-path or set QUINN_ORG_PATH."
        )

    rules_path = org_path / "config" / "rules.yaml"
    if not rules_path.exists():
        raise click.ClickException(
            f"No rules.yaml at {rules_path}. "
            f"`qn org rules disable` only edits the org's own rules file; "
            f"it cannot comment out the bundled default catalog."
        )

    text = rules_path.read_text()
    lines = text.splitlines(keepends=True)

    # Find the start of `  - id: <rule-id>` and the end of that rule block
    # (next sibling-list `  - id:` or non-indented line).
    start_idx = None
    target_marker = f"- id: {rule_id}"
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(target_marker) and (
            len(stripped) == len(target_marker)
            or not stripped[len(target_marker)].isalnum()
        ):
            start_idx = i
            break

    if start_idx is None:
        raise click.ClickException(f"rule '{rule_id}' not found in {rules_path}")

    # Capture indent of the matched line so we can find the next sibling.
    matched_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())

    end_idx = len(lines)  # default: comment out to EOF
    for j in range(start_idx + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            # blank line — keep scanning
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= matched_indent and line.lstrip().startswith("- "):
            # Next list-sibling. Stop before it.
            end_idx = j
            break
        if cur_indent < matched_indent:
            # De-indented past the rule block — stop.
            end_idx = j
            break

    new_lines = list(lines)
    for k in range(start_idx, end_idx):
        if new_lines[k].strip() == "":
            continue
        # Preserve trailing newline if present.
        line = new_lines[k]
        if line.endswith("\n"):
            new_lines[k] = "# " + line[:-1] + "\n"
        else:
            new_lines[k] = "# " + line

    rules_path.write_text("".join(new_lines))
    click.echo(f"disabled rule '{rule_id}' (commented out in {rules_path})")


# ---------------------------------------------------------------------------
# qn org rules add
# ---------------------------------------------------------------------------


@rules_cmd.command("add")
@pass_context
def add_cmd(ctx: Context) -> None:
    """Interactively scaffold a new rule and append it to rules.yaml.

    Prompts for id, severity, actions (comma-separated), and description.
    For ENCOURAGED / REQUIRED severities, also offers optional `pattern`
    fields. Writes to <org_path>/config/rules.yaml; creates the file with
    a `version: 1` header if it doesn't yet exist.
    """
    org_path = ctx.org_path
    if org_path is None:
        raise click.ClickException(
            "No org path specified.\n"
            "Use --org-path or set QUINN_ORG_PATH."
        )

    rule_id = click.prompt("rule id (kebab-case)", type=str).strip()
    if not rule_id:
        raise click.ClickException("rule id is required")
    # Light kebab-case sanity. Don't try to be a perfect validator; the
    # loader will catch garbage on the next `qn org rules validate`.
    if " " in rule_id:
        raise click.ClickException("rule id must not contain spaces (use-kebab-case)")

    severity = click.prompt(
        "severity",
        type=click.Choice(_VALID_SEVERITIES, case_sensitive=False),
    ).upper()

    actions_raw = click.prompt(
        "actions (comma-separated, e.g. 'qn-org.hire, qn-bd.create')",
        type=str,
    )
    actions = [a.strip() for a in actions_raw.split(",") if a.strip()]
    if not actions:
        raise click.ClickException("at least one action is required")

    description = click.prompt("description", type=str).strip()
    if not description:
        raise click.ClickException("description is required")

    # Optional pattern block for ENCOURAGED / REQUIRED.
    pattern_lines: list[str] = []
    if severity in ("ENCOURAGED", "REQUIRED"):
        if click.confirm("add a pattern? (regex/contains/glob match)", default=False):
            pattern_kind = click.prompt(
                "pattern.kind",
                type=click.Choice(["regex", "contains", "glob"], case_sensitive=False),
                default="regex",
            ).lower()
            pattern_target = click.prompt(
                "pattern.target (e.g. body, command, path, argument:<name>)",
                type=str,
                default="body",
            ).strip()
            pattern_expr = click.prompt("pattern.expr", type=str)
            pattern_lines = [
                "    pattern:\n",
                f"      kind: {pattern_kind}\n",
                f"      target: {pattern_target}\n",
                f"      expr: {_yaml_quote(pattern_expr)}\n",
            ]

        if click.confirm("add a scope? (env / worker_role)", default=False):
            scope_lines = ["    scope:\n"]
            scope_env = click.prompt(
                "scope.env (leave empty to skip)",
                type=str,
                default="",
                show_default=False,
            ).strip()
            if scope_env:
                scope_lines.append(f"      env: {scope_env}\n")
            scope_role = click.prompt(
                "scope.worker_role (leave empty to skip)",
                type=str,
                default="",
                show_default=False,
            ).strip()
            if scope_role:
                scope_lines.append(f"      worker_role: {scope_role}\n")
            # Only include scope: block if at least one key was provided.
            if len(scope_lines) > 1:
                pattern_lines.extend(scope_lines)

    rules_path = org_path / "config" / "rules.yaml"
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    if not rules_path.exists():
        rules_path.write_text("version: 1\nrules: []\n")

    existing_text = rules_path.read_text()

    # If the file is `rules: []`, replace it with `rules:` + the new entry.
    # Otherwise append the new entry under the existing list.
    new_block_lines = [
        f"  - id: {rule_id}\n",
        f"    severity: {severity}\n",
        "    actions:\n",
    ]
    for action in actions:
        new_block_lines.append(f"      - {_yaml_quote(action)}\n")
    new_block_lines.append(f"    description: {_yaml_quote(description)}\n")
    new_block_lines.extend(pattern_lines)
    new_block = "".join(new_block_lines)

    if "rules: []" in existing_text:
        new_text = existing_text.replace("rules: []", "rules:\n" + new_block.rstrip("\n"))
        if not new_text.endswith("\n"):
            new_text += "\n"
    else:
        suffix = "" if existing_text.endswith("\n") else "\n"
        new_text = existing_text + suffix + new_block

    rules_path.write_text(new_text)

    # Round-trip: reload to verify schema. If the new rule is malformed, the
    # loader raises and the operator gets an immediate signal to fix it.
    try:
        load_rules(org_path)
    except RuleSetLoadError as exc:
        click.echo(
            "WARNING: rule appended but rules.yaml no longer validates: "
            f"{exc}",
            err=True,
        )
        # Don't roll back — operator chose these inputs and should see the file
        # state. They can run `qn org rules validate` and fix manually.

    click.echo(f"added rule '{rule_id}' to {rules_path}")


def _yaml_quote(value: str) -> str:
    """Conservative YAML quoting for string scalars added by `qn org rules add`.

    PyYAML safe-loads an unquoted plain scalar in most cases, but characters
    like ':', '#', leading '!' / '*' / '&', and newlines need quoting.
    Always double-quote with backslash-escaping; that's a YAML 1.1 plain
    super-set that the loader will round-trip cleanly.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

"""qn org hire-team — instantiate a team from a template.

Per quinn-ai-iabn §F.2 + u0h2 §6 + cutg §6: thin Click wrapper around
TemplateOrchestrator.hire_team. The orchestrator does the real work; this
file is just CLI plumbing.
"""

from __future__ import annotations

import json
from typing import Optional

import click

from cli.commands.context import Context, pass_context
from cli.core.queries.worker import resolve_worker
from cli.core.rules import requires_rule_check
from cli.core.templates import TemplateOrchestrator, load_templates
from shared.exceptions import (
    ChannelNameCollision,
    HireTeamRollbackFailed,
    TemplateError,
)


def _parse_overrides(
    overrides: tuple[str, ...],
) -> tuple[dict[str, int], dict[str, int]]:
    """Parse --override flags into (size_overrides, cost_overrides) dicts.

    Forms:
      `engineer:3`            → size_overrides["engineer"] = 3
      `engineer:cost=70`      → cost_overrides["engineer"] = 70
    """
    size_overrides: dict[str, int] = {}
    cost_overrides: dict[str, int] = {}

    for raw in overrides:
        if ":" not in raw:
            raise click.BadParameter(
                f"--override must be of the form 'role:count' or 'role:cost=N'; "
                f"got {raw!r}"
            )
        role, _, value = raw.partition(":")
        if value.startswith("cost="):
            try:
                cost_overrides[role] = int(value.split("=", 1)[1])
            except ValueError:
                raise click.BadParameter(
                    f"--override cost must be int; got {value!r}"
                )
        else:
            try:
                size_overrides[role] = int(value)
            except ValueError:
                raise click.BadParameter(
                    f"--override count must be int; got {value!r}"
                )

    return size_overrides, cost_overrides


@click.command("hire-team")
@click.option("--template", required=True, help="Template name from templates.yaml.")
@click.option("--name", "team_name", required=True, help="Team-instance name.")
@click.option(
    "--manager",
    required=True,
    help="Existing worker (name or id) the team's manager will report to.",
)
@click.option(
    "--under",
    "parent_team_name",
    default=None,
    help="Parent team name (required iff template has 'requires').",
)
@click.option(
    "--role-override",
    "overrides",
    multiple=True,
    help="Repeatable: <role>:<count> or <role>:cost=<n>. (use --role-override, not --override which is reserved for rules engine)",
)
@click.option(
    "--worker-names",
    default=None,
    help='Optional JSON dict: {"role": ["name1","name2"]}. Else auto-generated.',
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate inputs only; do not create anything.",
)
@requires_rule_check("qn-org.hire-team")
@pass_context
def hire_team_cmd(
    ctx: Context,
    template: str,
    team_name: str,
    manager: str,
    parent_team_name: Optional[str],
    overrides: tuple[str, ...],
    worker_names: Optional[str],
    dry_run: bool,
) -> None:
    """Hire an entire team from a template in one operation.

    \b
    Examples:
      qn org hire-team --template=product_team --name=mobile --manager=alice
      qn org hire-team --template=launch_pod --name=auth-redesign \\
          --manager=alice --under=mobile
      qn org hire-team --template=product_team --name=web --manager=alice \\
          --override engineer:3 --override designer:cost=55
    """
    # Resolve manager name -> id (the orchestrator wants the worker_id).
    manager_worker = resolve_worker(ctx.db, manager)
    if manager_worker is None:
        raise click.ClickException(f"Manager not found: {manager!r}")

    size_overrides, cost_overrides = _parse_overrides(overrides)

    parsed_worker_names: dict[str, list[str]] = {}
    if worker_names:
        try:
            parsed = json.loads(worker_names)
            if not isinstance(parsed, dict):
                raise ValueError("must be a JSON object")
            for k, v in parsed.items():
                if not isinstance(v, list):
                    raise ValueError(f"value for role {k!r} must be a list")
                parsed_worker_names[str(k)] = [str(name) for name in v]
        except (json.JSONDecodeError, ValueError) as exc:
            raise click.BadParameter(f"--worker-names: {exc}")

    registry = load_templates(ctx.org_path)
    orch = TemplateOrchestrator(ctx=ctx, db=ctx.db, registry=registry)

    try:
        result = orch.hire_team(
            template_name=template,
            team_name=team_name,
            manager_id=manager_worker.id,
            parent_team_name=parent_team_name,
            size_overrides=size_overrides,
            cost_overrides=cost_overrides,
            worker_names=parsed_worker_names,
            dry_run=dry_run,
        )
    except HireTeamRollbackFailed as exc:
        raise click.ClickException(
            f"hire-team failed AND rollback failed — manual cleanup required.\n"
            f"Original: {exc.original}\n"
            f"Rollback errors: {len(exc.rollback_errors)}"
        )
    except (TemplateError, ChannelNameCollision) as exc:
        raise click.ClickException(str(exc))

    if result.rolled_back:
        raise click.ClickException(
            f"hire-team rolled back: {result.failure_reason}"
        )

    prefix = "[dry-run] " if dry_run else ""
    click.echo(f"{prefix}✓ Team '{team_name}' instantiated from template '{template}'")
    click.echo(f"  team_id: {result.team_id}")
    if result.channel_id:
        click.echo(f"  channel_id: {result.channel_id}")
    click.echo(f"  workers: {len(result.worker_ids)}")
    for wid in result.worker_ids:
        click.echo(f"    - {wid}")
    if result.okr_ids:
        click.echo(f"  initial OKRs: {len(result.okr_ids)}")


@click.group("templates")
def templates_cmd():
    """Inspect and validate org-template definitions."""


@templates_cmd.command("list")
@pass_context
def templates_list(ctx: Context) -> None:
    """List all templates in the org's templates.yaml (or default catalog)."""
    registry = load_templates(ctx.org_path)
    if not registry.templates:
        click.echo("(no templates defined)")
        return
    click.echo(f"{'NAME':<28} {'MEMBERS':<7} {'REQUIRES':<24} DESCRIPTION")
    for tmpl in registry.templates:
        total_members = sum(m.count for m in tmpl.members)
        requires = ", ".join(tmpl.requires) or "-"
        desc = tmpl.description if len(tmpl.description) <= 50 else tmpl.description[:47] + "..."
        click.echo(f"{tmpl.name:<28} {total_members:<7} {requires:<24} {desc}")


@templates_cmd.command("show")
@click.argument("template_name")
@pass_context
def templates_show(ctx: Context, template_name: str) -> None:
    """Print the full definition of one template."""
    from shared.exceptions import TemplateNotFound

    registry = load_templates(ctx.org_path)
    try:
        tmpl = registry.get(template_name)
    except TemplateNotFound:
        raise click.ClickException(f"Template not found: {template_name!r}")

    click.echo(f"name:        {tmpl.name}")
    click.echo(f"description: {tmpl.description}")
    if tmpl.requires:
        click.echo(f"requires:    {list(tmpl.requires)}")
    if tmpl.ttl_hours:
        click.echo(f"ttl_hours:   {tmpl.ttl_hours}")
    if tmpl.channel:
        click.echo(f"channel:     auto_create={tmpl.channel.auto_create} "
                   f"name_template='{tmpl.channel.name_template}'")
    click.echo("members:")
    for m in tmpl.members:
        manager_marker = " (manager)" if m.is_manager else ""
        click.echo(f"  - role={m.role} count={m.count} cost={m.cost}{manager_marker}")
    if tmpl.initial_okrs:
        click.echo(f"initial_okrs: {len(tmpl.initial_okrs)}")
        for o in tmpl.initial_okrs:
            click.echo(f"  - {o.title}")


@templates_cmd.command("validate")
@pass_context
def templates_validate(ctx: Context) -> None:
    """Run the loader against the org's templates.yaml; exit non-zero on error."""
    try:
        registry = load_templates(ctx.org_path)
    except Exception as exc:
        click.echo(f"templates.yaml validation failed: {exc}", err=True)
        raise click.exceptions.Exit(1)
    click.echo(f"✓ templates.yaml valid ({len(registry.templates)} templates)")

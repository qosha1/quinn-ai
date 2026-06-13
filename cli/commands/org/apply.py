"""
qn org apply command.

Reconcile an organization against a declarative org.yml: create what's missing
(teams, managers, declared members, delegations, OKRs) and leave what exists
alone. Idempotent — re-running the same spec is a no-op; running an edited spec
applies only the delta. Initializes the org first if it doesn't exist yet.
"""

from pathlib import Path
from typing import Optional

import click

from cli.commands.context import Context, pass_context


@click.command("apply")
@click.argument("spec_path", type=click.Path(exists=False))
@pass_context
def apply_cmd(ctx: Context, spec_path: str) -> None:
    """Apply a declarative org.yml, idempotently.

    \b
    Examples:
      qn org apply org.yml          # create-or-reconcile against the spec
    """
    from cli.core.org_spec import OrgSpecError, apply_org_spec, load_org_spec

    org_path: Optional[Path] = ctx.org_path or Path.cwd()
    try:
        spec = load_org_spec(Path(spec_path))
        result = apply_org_spec(spec, target_path=org_path, update=True)
    except OrgSpecError as e:
        raise click.ClickException(str(e))

    click.echo(f"Applied organization '{spec.name}' at {result.org_path}")
    click.echo(
        f"Teams: {len(result.team_ids)}  "
        f"Workers: {len(result.worker_ids)}  "
        f"OKRs: {len(result.okr_ids)}"
    )
    for warning in result.warnings:
        click.echo(f"Warning: {warning}", err=True)

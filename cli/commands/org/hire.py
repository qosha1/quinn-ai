"""
qn org hire command.

Create a new worker under a manager in the organization.
"""

import json
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker, InsufficientHiringAuthority, MaxReportsExceeded
from cli.core.queries import get_worker_by_name


@click.command()
@click.option(
    "--name",
    required=True,
    help="Name for the new worker.",
)
@click.option(
    "--role",
    required=True,
    help="Role for the new worker (e.g., 'developer', 'qa', 'designer').",
)
@click.option(
    "--manager",
    required=True,
    help="Manager worker name or ID. The new worker reports to this manager.",
)
@click.option(
    "--cost",
    type=int,
    default=50,
    help="Cost score 0-100. Higher = more expensive provider. (default: 50)",
)
@click.option(
    "--skills",
    type=str,
    default="{}",
    help='Skills as JSON object (e.g., \'{"coding": 80, "reasoning": 60}\').',
)
@pass_context
def hire_cmd(
    ctx: Context,
    name: str,
    role: str,
    manager: str,
    cost: int,
    skills: str,
):
    """Hire a new worker into the organization.

    Creates a new worker under the specified manager. The manager must have
    sufficient hiring authority and available budget.

    \b
    Examples:
      qn org hire --name alice --role developer --manager ceo
      qn org hire --name bob --role qa --manager alice --cost 30
      qn org hire --name carol --role designer --manager ceo --skills '{"design": 90}'
      qn org hire --name dave --role developer --manager alice
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Validate cost
    if not 0 <= cost <= 100:
        raise click.ClickException("Cost must be between 0 and 100.")

    # Parse skills JSON
    try:
        skills_dict = json.loads(skills)
        if not isinstance(skills_dict, dict):
            raise ValueError("Skills must be a JSON object")
        # Validate skill values
        for skill_name, value in skills_dict.items():
            if not isinstance(value, (int, float)) or not 0 <= value <= 100:
                raise ValueError(f"Skill '{skill_name}' must be a number 0-100")
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid skills JSON: {e}")
    except ValueError as e:
        raise click.ClickException(str(e))

    db = open_database(db_path)

    try:
        # Find manager worker
        manager_data = get_worker_by_name(db, manager)
        if not manager_data:
            # Try by ID
            try:
                manager_worker = Worker.get(db, manager)
            except (ValueError, KeyError):
                raise click.ClickException(
                    f"Manager '{manager}' not found.\n"
                    "Use 'qn org status' to see available workers."
                )
        else:
            manager_worker = Worker.get(db, manager_data.id)

        # Check manager's hiring authority
        can_hire, reason = manager_worker.can_hire(role, cost)
        if not can_hire:
            raise click.ClickException(
                f"Manager '{manager_worker.name}' cannot hire this worker:\n"
                f"  {reason}\n\n"
                "Tips:\n"
                "  - Check manager's hiring_authority_scope\n"
                "  - Check manager's delegated_budget\n"
                "  - Check manager's max_reports limit"
            )

        # Hire the worker
        try:
            new_worker = manager_worker.hire(
                name=name,
                role=role,
                skills=skills_dict,
                cost=cost,
            )
        except InsufficientHiringAuthority as e:
            raise click.ClickException(f"Hiring failed: {e}")
        except MaxReportsExceeded as e:
            raise click.ClickException(
                f"Manager '{manager_worker.name}' has reached max direct reports ({e.max_reports}).\n"
                "Consider promoting an existing worker to manager to distribute leadership."
            )

        click.echo(f"Hired '{new_worker.name}' ({new_worker.role})")
        click.echo(f"  ID: {new_worker.id}")
        click.echo(f"  Manager: {manager_worker.name}")
        click.echo(f"  Team: {manager_worker.team_id}")
        click.echo(f"  Cost: {cost}")
        if skills_dict:
            click.echo(f"  Skills: {json.dumps(skills_dict)}")

        # Start session (hire == spawn + start + onboard)
        click.echo("")
        click.echo("Starting worker session...")
        try:
            _start_workday_for_hire(ctx, new_worker)
            click.echo(f"Session started for {new_worker.name}")
        except Exception as e:
            click.echo(f"Warning: Failed to start session: {e}")
            click.echo("You can start manually with: qn org start")

        click.echo("")
        click.echo("Next steps:")
        click.echo(f"  qn org status                    # See org status")
        click.echo(f"  qn org observe {new_worker.name}  # Watch worker activity")

    finally:
        db.close()


def _start_workday_for_hire(ctx: Context, worker: Worker) -> None:
    """Start a worker session using org provider defaults."""
    from cli.core.config import get_org_config_path
    from cli.core.provider import load_providers_from_config
    from cli.commands.org.session_utils import spawn_worker_session

    config_path = get_org_config_path(ctx.org_path) / "providers.yaml"
    registry = load_providers_from_config(config_path)
    provider = registry.select_for_worker(worker.cost, worker.skills)[0]

    # Transition lifecycle for onboarding on first hire
    if worker.lifecycle_status == "pending":
        worker.start_onboarding()
        worker.complete_onboarding()

    spawn_worker_session(
        worker=worker,
        provider=provider.name,
        command=provider.cli_command,
        args_str="--dangerously-skip-permissions",
    )

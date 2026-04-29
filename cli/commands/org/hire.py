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
from cli.core.queries import resolve_worker
from shared.exceptions import WorkerNotFound


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
        # Resolve selector (id, name, or unique role).
        manager_data = resolve_worker(db, manager)
        if not manager_data:
            raise click.ClickException(
                f"Manager '{manager}' not found.\n"
                "Use 'qn org status' to see available workers."
            )
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

        # Grant baseline write permission so the worker can use bd-backed
        # commands like 'qn wrkr report' (which create bead records).
        # Without this, every non-CEO command that writes a bead fails
        # with BeadPermissionError (quinn-ai-ad95). The CEO bypasses the
        # check by running bd commands without a worker_id; reports run
        # *as* the worker so they need an actual permission row.
        from cli.core.queries import grant_permission
        from cli.core.constants.permissions import PERM_LEVEL_WRITE
        grant_permission(
            db,
            grantee_type="worker",
            grantee_id=new_worker.id,
            level=PERM_LEVEL_WRITE,
            granted_by=manager_worker.id,
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
        from shared.exceptions import NoBudgetAllocationError
        try:
            _start_workday_for_hire(ctx, new_worker)
            click.echo(f"Session started for {new_worker.name}")
        except NoBudgetAllocationError:
            # Fresh-org case: managers haven't allocated per-worker budget yet.
            # Not really a failure — frame it as the expected 2-step flow.
            # Single copy-pasteable command so an autonomous CEO can chain it
            # without remembering the order (quinn-ai-xdwo).
            click.echo(
                f"Worker created. Run this to give them a budget and bring "
                f"the session online:"
            )
            click.echo(
                f"  qn org budget allocate {new_worker.name} <amount> "
                f"&& qn org start --worker {new_worker.name}"
            )
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
    """Start a worker session using worker's preferred provider or org defaults."""
    from cli.core.config import get_org_config_path
    from cli.core.config.loaders import load_providers_config
    from cli.core.onboarding import (
        get_worker_env_vars,
        prepare_worker_onboarding,
    )
    from cli.core.storage import StorageManager
    from cli.providers.registry import load_providers_from_config
    from cli.commands.org.session_utils import spawn_worker_session

    config_path = get_org_config_path(ctx.org_path) / "providers.yaml"
    registry = load_providers_from_config(config_path)

    # Use worker's preferred_provider if set, otherwise select based on cost/skills
    if worker.preferred_provider:
        # Worker has explicit preference - use it
        provider_name = worker.preferred_provider
        cli_command = "claude"  # Default command - will be overridden by adapter
        # Try to get provider info if it exists in the registry
        if registry.has(provider_name):
            provider = registry.get(provider_name)
            cli_command = provider.cli_command
    else:
        # Try cost-based API provider selection first.
        try:
            provider = registry.select_for_worker(worker.cost, worker.skills)[0]
            provider_name = provider.name
            cli_command = provider.cli_command
        except ValueError:
            # No API provider can satisfy — fall back to the org's session
            # default from providers.yaml. Cost selection only applies to
            # API providers (anthropic, openai); session-CLI providers like
            # claude_code use the user's subscription, not metered API.
            providers_cfg = load_providers_config(config_path)
            provider_name = providers_cfg.default or "claude_code"
            cli_command = "claude"

    # Transition lifecycle for onboarding on first hire
    if worker.lifecycle_status == "pending":
        worker.start_onboarding()
        worker.complete_onboarding()

    # quinn-ai-3gwh: hired workers need QUINN_WORKER_ID + QUINN_ORG_PATH +
    # WORKER_STORAGE etc. in their tmux env so msgr / qn-bd / workspace
    # awareness work. Without this, every msgr or qn-bd call from a hired
    # worker errors with 'QUINN_WORKER_ID not set'. The CEO already gets
    # these via qn org start; mirror that here for hired workers.
    onboarding_ctx = prepare_worker_onboarding(ctx.db, worker.id, ctx.org_path)
    storage = StorageManager(ctx.org_path, ctx.db)
    worker_dir = storage.get_worker_path(worker.id)
    env_vars = get_worker_env_vars(onboarding_ctx, ctx.org_path, ctx.db)

    spawn_worker_session(
        worker=worker,
        provider=provider_name,
        command=cli_command,
        args_str="--dangerously-skip-permissions",
        working_directory=worker_dir,
        env_vars=env_vars,
    )

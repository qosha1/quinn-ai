"""
qn board status command.

Show organization status dashboard for board oversight.
Displays workers, sessions, budget, and alerts summary.
"""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.queries import (
    get_all_budget_pools,
    get_current_allocation,
    get_workers_by_status,
    get_workers_by_runtime_status,
)


def _format_budget_bar(spent: float, total: float, width: int = 10) -> str:
    """Format a progress bar for budget display."""
    if total <= 0:
        return "[" + "-" * width + "]"

    pct = min(spent / total, 1.0)
    filled = int(pct * width)
    empty = width - filled
    return "[" + "#" * filled + "-" * empty + "]"


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@pass_context
def status_cmd(ctx: Context, as_json: bool):
    """Show organization status dashboard.

    Displays org lifecycle state, workers, sessions, budget, and alerts.
    This is the primary board oversight view.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        # Reconcile runtime_status against tmux reality before reading
        # session counts (quinn-ai-pwjp).
        from cli.core.worker.session_manager import reconcile_runtime_states
        reconcile_runtime_states(db)

        org = Org.load(db)

        # Collect status data
        status_data = {
            "org_path": str(org_path),
            "status": org.status,
            "workers": {
                "total": org.worker_count,
                "active": org.active_worker_count,
                "sessions": org.active_session_count,
            },
            "budget": {},
            "alerts": [],
        }

        # Get worker breakdown
        pending_workers = len(get_workers_by_status(db, "pending"))
        onboarding_workers = len(get_workers_by_status(db, "onboarding"))
        active_workers = len(get_workers_by_status(db, "active"))
        offboarding_workers = len(get_workers_by_status(db, "offboarding"))
        terminated_workers = len(get_workers_by_status(db, "terminated"))

        # Get session breakdown
        starting_sessions = len(get_workers_by_runtime_status(db, "starting"))
        running_sessions = len(get_workers_by_runtime_status(db, "running"))
        idle_sessions = len(get_workers_by_runtime_status(db, "idle"))
        stopped_sessions = len(get_workers_by_runtime_status(db, "stopped"))
        crashed_sessions = len(get_workers_by_runtime_status(db, "crashed"))

        # Get budget info
        pools = get_all_budget_pools(db)
        total_budget = sum(p.total_credits for p in pools)

        # Get CEO budget allocation if available
        ceo_spent = 0.0
        ceo_allocated = 0.0
        if org.ceo_worker_id:
            ceo_alloc = get_current_allocation(db, org.ceo_worker_id)
            if ceo_alloc:
                ceo_spent = ceo_alloc.spent_credits
                ceo_allocated = ceo_alloc.allocated_credits

        status_data["budget"] = {
            "total_pool": total_budget,
            "ceo_allocated": ceo_allocated,
            "ceo_spent": ceo_spent,
        }

        # Get alerts (placeholder - will be populated when alert system exists)
        # For now, generate basic health alerts
        alerts = []

        # Check for crashed sessions
        if crashed_sessions > 0:
            alerts.append({
                "priority": "P0",
                "message": f"{crashed_sessions} worker session(s) crashed",
            })

        # Check budget usage
        if ceo_allocated > 0:
            budget_pct = (ceo_spent / ceo_allocated) * 100
            if budget_pct >= 95:
                alerts.append({
                    "priority": "P0",
                    "message": f"Budget nearly exhausted ({budget_pct:.1f}%)",
                })
            elif budget_pct >= 80:
                alerts.append({
                    "priority": "P1",
                    "message": f"Budget at {budget_pct:.1f}%",
                })

        # Check for idle workers
        if idle_sessions > 3:
            alerts.append({
                "priority": "P2",
                "message": f"{idle_sessions} workers idle",
            })

        status_data["alerts"] = alerts

        if as_json:
            import json
            click.echo(json.dumps(status_data, indent=2))
            return

        # Display formatted output
        click.echo(f"Organization: {org_path}")
        click.echo(f"Status: {org.status}")
        click.echo("")

        # Workers section
        click.echo("Workers:")
        click.echo(f"  Total: {org.worker_count}")
        click.echo(f"  Pending: {pending_workers}")
        click.echo(f"  Onboarding: {onboarding_workers}")
        click.echo(f"  Active: {active_workers}")
        click.echo(f"  Offboarding: {offboarding_workers}")
        click.echo(f"  Terminated: {terminated_workers}")
        click.echo("")

        # Sessions section
        click.echo("Sessions:")
        click.echo(f"  Starting: {starting_sessions}")
        click.echo(f"  Running: {running_sessions}")
        click.echo(f"  Idle: {idle_sessions}")
        click.echo(f"  Stopped: {stopped_sessions}")
        click.echo(f"  Crashed: {crashed_sessions}")
        click.echo("")

        # Budget section
        click.echo("Budget:")
        click.echo(f"  Pool Total: {total_budget:.2f} cr")
        if ceo_allocated > 0:
            budget_pct = (ceo_spent / ceo_allocated) * 100
            bar = _format_budget_bar(ceo_spent, ceo_allocated)
            click.echo(f"  CEO Allocation: {ceo_allocated:.2f} cr")
            click.echo(f"  CEO Spent: {ceo_spent:.2f} cr ({budget_pct:.1f}%) {bar}")
        else:
            click.echo("  CEO Allocation: (none)")
        click.echo("")

        # CEO info
        if org.ceo:
            click.echo("CEO:")
            click.echo(f"  Name: {org.ceo.name}")
            click.echo(f"  Role: {org.ceo.role}")
            click.echo(f"  Lifecycle: {org.ceo.lifecycle_status}")
            if org.ceo.runtime_status:
                click.echo(f"  Runtime: {org.ceo.runtime_status}")
            click.echo("")

        # Alerts section
        if alerts:
            click.echo(f"Alerts ({len(alerts)}):")
            for alert in alerts:
                click.echo(f"  [{alert['priority']}] {alert['message']}")
            click.echo("")
            click.echo("Run 'qn board alerts' for details.")
        else:
            click.echo("Alerts: None")

    finally:
        db.close()

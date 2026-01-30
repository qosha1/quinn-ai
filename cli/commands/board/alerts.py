"""
qn board alerts command.

View and manage system alerts for board oversight.
Per CLAUDE.md: Board = Gutterguards. Intervene only when org is off-track.
"""

import json
from datetime import datetime
from typing import Optional

import click

from commands.context import pass_context, Context
from core.db import open_database, get_org_db_path
from shared.enums import Priority
from core.queries import (
    get_all_budget_pools,
    get_current_allocation,
    get_workers_by_runtime_status,
    generate_id,
)


def _get_active_alerts(db) -> list[dict]:
    """Generate active alerts based on current org state.

    This is a simplified alert system. The full alert monitoring system
    would store alerts in a board_alerts table and run continuous monitors.
    For MVP, we derive alerts from current state.
    """
    alerts = []

    # Check for crashed sessions (P0)
    crashed = get_workers_by_runtime_status(db, "crashed")
    for state in crashed:
        alerts.append({
            "id": f"alert-crash-{state.worker_id[:8]}",
            "priority": Priority.P0.value,
            "category": "session",
            "title": f"Worker session crashed",
            "details": f"Worker {state.worker_id} session crashed",
            "worker_id": state.worker_id,
            "detected_at": datetime.now().isoformat(),
        })

    # Check for stale sessions (workers idle too long)
    idle_workers = get_workers_by_runtime_status(db, "idle")
    for state in idle_workers:
        if state.last_activity:
            last_activity = state.last_activity
            if isinstance(last_activity, str):
                last_activity = datetime.fromisoformat(last_activity)
            idle_hours = (datetime.now() - last_activity).total_seconds() / 3600
            if idle_hours > 2:
                alerts.append({
                    "id": f"alert-idle-{state.worker_id[:8]}",
                    "priority": Priority.P2.value,
                    "category": "performance",
                    "title": f"Worker idle for {idle_hours:.1f}h",
                    "details": f"Worker {state.worker_id} has been idle for extended period",
                    "worker_id": state.worker_id,
                    "detected_at": datetime.now().isoformat(),
                })

    # Check budget usage
    pools = get_all_budget_pools(db)
    if pools:
        # Get CEO allocation for budget check
        from core.org import Org
        org = Org.load(db)
        if org.ceo_worker_id:
            alloc = get_current_allocation(db, org.ceo_worker_id)
            if alloc and alloc.allocated_credits > 0:
                budget_pct = (alloc.spent_credits / alloc.allocated_credits) * 100
                if budget_pct >= 95:
                    alerts.append({
                        "id": f"alert-budget-critical",
                        "priority": Priority.P0.value,
                        "category": "budget",
                        "title": f"Budget nearly exhausted ({budget_pct:.1f}%)",
                        "details": f"Spent {alloc.spent_credits:.2f} of {alloc.allocated_credits:.2f} credits",
                        "detected_at": datetime.now().isoformat(),
                    })
                elif budget_pct >= 80:
                    alerts.append({
                        "id": f"alert-budget-warning",
                        "priority": Priority.P1.value,
                        "category": "budget",
                        "title": f"Budget at {budget_pct:.1f}%",
                        "details": f"Spent {alloc.spent_credits:.2f} of {alloc.allocated_credits:.2f} credits",
                        "detected_at": datetime.now().isoformat(),
                    })

    return sorted(alerts, key=lambda a: (a["priority"], a["detected_at"]))


@click.command()
@click.option("--priority", "-p", type=click.Choice(["P0", "P1", "P2"]),
              help="Filter by priority level")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--unresolved", is_flag=True, help="Show only unresolved alerts")
@pass_context
def alerts_cmd(ctx: Context, priority: Optional[str], as_json: bool, unresolved: bool):
    """View active system alerts.

    Displays alerts generated from org health monitoring.
    Priority levels:
      P0 - Requires immediate attention (crashes, budget exhaustion)
      P1 - High priority (budget warnings, deadline misses)
      P2 - Normal priority (performance issues, idle workers)
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
        alerts = _get_active_alerts(db)

        # Filter by priority if specified
        if priority:
            alerts = [a for a in alerts if a["priority"] == priority]

        if as_json:
            click.echo(json.dumps({"alerts": alerts}, indent=2))
            return

        click.echo(f"Active Alerts - {org_path}")
        click.echo("")

        if not alerts:
            click.echo("No active alerts.")
            return

        # Group by priority
        p0_alerts = [a for a in alerts if a["priority"] == Priority.P0.value]
        p1_alerts = [a for a in alerts if a["priority"] == Priority.P1.value]
        p2_alerts = [a for a in alerts if a["priority"] == Priority.P2.value]

        if p0_alerts:
            click.echo("=== P0 (Requires Immediate Attention) ===")
            for alert in p0_alerts:
                click.echo(f"  [{alert['id']}] {alert['title']}")
                click.echo(f"      Category: {alert['category']}")
                click.echo(f"      Details: {alert['details']}")
                click.echo(f"      Detected: {alert['detected_at']}")
                click.echo("")

        if p1_alerts:
            click.echo("=== P1 (High Priority) ===")
            for alert in p1_alerts:
                click.echo(f"  [{alert['id']}] {alert['title']}")
                click.echo(f"      Category: {alert['category']}")
                click.echo(f"      Details: {alert['details']}")
                click.echo(f"      Detected: {alert['detected_at']}")
                click.echo("")

        if p2_alerts:
            click.echo("=== P2 (Normal Priority) ===")
            for alert in p2_alerts:
                click.echo(f"  [{alert['id']}] {alert['title']}")
                click.echo(f"      Category: {alert['category']}")
                click.echo(f"      Details: {alert['details']}")
                click.echo(f"      Detected: {alert['detected_at']}")
                click.echo("")

        click.echo(f"Total: {len(alerts)} alert(s)")

    finally:
        db.close()

"""
qn board health command.

Show detailed health status and issues for workers.
Provides copyable text output for debugging.
"""

import click
from pathlib import Path

from commands.context import pass_context, Context
from core.db import open_database, get_org_db_path


def _get_health_status(org_path: Path) -> dict:
    """Get health status by importing the Board UI connection logic."""
    # Import here to avoid circular dependencies
    import sys
    from pathlib import Path

    # Add terminal-app to path
    terminal_app_path = Path(__file__).parent.parent.parent.parent / "terminal-app" / "src"
    if str(terminal_app_path) not in sys.path:
        sys.path.insert(0, str(terminal_app_path))

    from board_ui.services.org_connection import QuinnAIOrgConnection

    conn = QuinnAIOrgConnection(org_path)
    health = conn.get_health_status()

    return health


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@pass_context
def health_cmd(ctx: Context, as_json: bool):
    """Show detailed health status and issues.

    Displays worker health issues in copyable text format.
    Useful for debugging and sharing error messages.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    try:
        health = _get_health_status(org_path)

        if as_json:
            import json
            # Convert to JSON-serializable format
            output = {
                "overall_score": health.overall_score,
                "workers_with_issues": health.workers_with_issues,
                "total_workers": health.total_workers,
                "issues": [
                    {
                        "worker_id": issue.worker_id,
                        "worker_name": issue.worker_name,
                        "issue_type": issue.issue_type,
                        "severity": issue.severity,
                        "message": issue.message,
                    }
                    for issue in health.issues
                ]
            }
            click.echo(json.dumps(output, indent=2))
            return

        # Display formatted output
        click.echo(f"Organization Health: {org_path}")
        click.echo(f"Overall Score: {health.overall_score}")
        click.echo(f"Workers: {health.total_workers} total, {health.workers_with_issues} with issues")
        click.echo("")

        if not health.issues:
            click.echo("No issues detected.")
            return

        # Group issues by worker
        issues_by_worker = {}
        for issue in health.issues:
            worker_key = f"{issue.worker_name} ({issue.worker_id})"
            if worker_key not in issues_by_worker:
                issues_by_worker[worker_key] = []
            issues_by_worker[worker_key].append(issue)

        # Display issues grouped by worker
        click.echo(f"Issues ({len(health.issues)} total):")
        click.echo("")

        for worker_key, worker_issues in issues_by_worker.items():
            click.echo(f"{worker_key}:")
            for issue in worker_issues:
                severity_emoji = {
                    "critical": "🔴",
                    "warning": "🟡",
                    "info": "🔵"
                }.get(issue.severity, "⚪")
                click.echo(f"  {severity_emoji} [{issue.severity.upper()}] {issue.issue_type}")
                click.echo(f"     {issue.message}")
            click.echo("")

    except Exception as e:
        raise click.ClickException(f"Failed to get health status: {e}")

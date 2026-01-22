"""
qn org chart command group.

Provides org-chart visibility for the organization:
- qn org chart - Show org structure as tree
- qn org chart diff - Show changes since last commit (git diff)
- qn org chart history - Show git log of changes
- qn org chart export - Export org-chart as yaml or json
"""

import json
import subprocess
from pathlib import Path
from typing import Optional

import click
import yaml

from cli.commands.context import pass_context, Context
from cli.core.org_chart import (
    ORG_CHART_DIR,
    ORG_CHART_CURRENT,
)


@click.group()
def chart_cmd():
    """View organization chart.

    Display org structure, track changes, and export org-chart data.
    """
    pass


@chart_cmd.command("show")
@pass_context
def chart_show(ctx: Context):
    """Show current org structure as tree.

    Displays the organization hierarchy with worker names, roles, and lifecycle status.

    Example output:
    \b
    Organization Structure:
    - Alice (CEO) - active
       - Bob (Director of Engineering) - active
          - Carol (Senior Engineer) - active
          - Dave (Junior Engineer) - onboarding
       - Eve (Director of Operations) - active
    """
    org_path = ctx.org_path
    chart_path = org_path / ORG_CHART_DIR / ORG_CHART_CURRENT

    if not chart_path.exists():
        raise click.ClickException(
            f"Org-chart not found at {chart_path}\n"
            "Run 'qn org init' to initialize the organization."
        )

    with open(chart_path) as f:
        org_chart = yaml.safe_load(f)

    workers = org_chart.get("workers", {})
    hierarchy = org_chart.get("hierarchy", {})
    root_id = hierarchy.get("root")

    if not root_id or root_id not in workers:
        click.echo("No workers found in org-chart.")
        return

    click.echo("Organization Structure:")
    _print_worker_tree(workers, root_id)


def _print_worker_tree(
    workers: dict,
    worker_id: str,
    prefix: str = "",
    is_last: bool = True,
    is_root: bool = True,
) -> None:
    """Recursively print worker tree with unicode box-drawing characters.

    Args:
        workers: Dict of worker_id -> worker data
        worker_id: Current worker to print
        prefix: Prefix string for current line (built from parent lines)
        is_last: Whether this is the last sibling in the current level
        is_root: Whether this is the root node
    """
    worker = workers.get(worker_id)
    if not worker:
        return

    # Format: Name (Role) - lifecycle
    name = worker.get("name", "Unknown")
    role = worker.get("role", "Unknown")
    lifecycle = worker.get("lifecycle", "unknown")

    # Build the tree connector using unicode box-drawing characters
    if is_root:
        connector = ""
    elif is_last:
        connector = "|_ "  # Last child: corner
    else:
        connector = "|- "  # Middle child: tee

    click.echo(f"{prefix}{connector}{name} ({role}) - {lifecycle}")

    # Print reports recursively
    reports = worker.get("reports", [])
    for i, report_id in enumerate(reports):
        # Build new prefix for children
        if is_root:
            new_prefix = "   "
        elif is_last:
            new_prefix = prefix + "   "  # Last sibling: no vertical line
        else:
            new_prefix = prefix + "|  "  # Middle sibling: vertical line continues

        is_last_report = (i == len(reports) - 1)
        _print_worker_tree(workers, report_id, new_prefix, is_last_report, False)


@chart_cmd.command("diff")
@click.option("--cached", is_flag=True, help="Show staged changes only")
@pass_context
def chart_diff(ctx: Context, cached: bool):
    """Show org-chart changes since last commit.

    Displays git diff for the org-chart/current.yaml file, showing what
    has changed since the last commit.
    """
    org_path = ctx.org_path
    chart_rel_path = f"{ORG_CHART_DIR}/{ORG_CHART_CURRENT}"
    chart_path = org_path / ORG_CHART_DIR / ORG_CHART_CURRENT

    if not chart_path.exists():
        raise click.ClickException(
            f"Org-chart not found at {chart_path}\n"
            "Run 'qn org init' to initialize the organization."
        )

    # Check if this is a git repo
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=org_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise click.ClickException(
            "Not a git repository. Git tracking is required for diff."
        )

    # Build git diff command
    cmd = ["git", "diff"]
    if cached:
        cmd.append("--cached")
    cmd.append("--")
    cmd.append(chart_rel_path)

    result = subprocess.run(
        cmd,
        cwd=org_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise click.ClickException(f"Git diff failed: {result.stderr}")

    if result.stdout.strip():
        click.echo(result.stdout)
    else:
        click.echo("No changes to org-chart since last commit.")


@chart_cmd.command("history")
@click.option("--limit", "-n", default=10, help="Number of commits to show (default: 10)")
@click.option("--oneline", is_flag=True, help="Show compact one-line format")
@pass_context
def chart_history(ctx: Context, limit: int, oneline: bool):
    """Show git history of org-chart changes.

    Displays the commit history for org-chart files, showing when
    workers were hired, terminated, or updated.
    """
    org_path = ctx.org_path
    chart_dir_path = org_path / ORG_CHART_DIR

    if not chart_dir_path.exists():
        raise click.ClickException(
            f"Org-chart directory not found at {chart_dir_path}\n"
            "Run 'qn org init' to initialize the organization."
        )

    # Check if this is a git repo
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=org_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise click.ClickException(
            "Not a git repository. Git tracking is required for history."
        )

    # Build git log command
    cmd = ["git", "log", f"-{limit}"]
    if oneline:
        cmd.append("--oneline")
    else:
        cmd.extend(["--format=%h %ad %s", "--date=short"])
    cmd.append("--")
    cmd.append(str(ORG_CHART_DIR))

    result = subprocess.run(
        cmd,
        cwd=org_path,
        capture_output=True,
        text=True,
    )

    # Handle empty repo or no commits on org-chart
    if result.returncode != 0:
        if "does not have any commits yet" in result.stderr:
            click.echo("No git history found for org-chart.")
            click.echo("The repository has no commits yet.")
            return
        raise click.ClickException(f"Git log failed: {result.stderr}")

    if result.stdout.strip():
        click.echo("Org-chart History:")
        click.echo(result.stdout)
    else:
        click.echo("No git history found for org-chart.")
        click.echo("The org-chart may not have been committed yet.")


@chart_cmd.command("export")
@click.option(
    "--format", "-f", "output_format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format (default: yaml)"
)
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@pass_context
def chart_export(ctx: Context, output_format: str, output: Optional[str]):
    """Export org-chart in yaml or json format.

    Exports the current org-chart data structure to stdout or a file.
    Useful for backups, migrations, or external tooling.
    """
    org_path = ctx.org_path
    chart_path = org_path / ORG_CHART_DIR / ORG_CHART_CURRENT

    if not chart_path.exists():
        raise click.ClickException(
            f"Org-chart not found at {chart_path}\n"
            "Run 'qn org init' to initialize the organization."
        )

    with open(chart_path) as f:
        org_chart = yaml.safe_load(f)

    if output_format == "json":
        content = json.dumps(org_chart, indent=2)
    else:
        content = yaml.dump(org_chart, default_flow_style=False, sort_keys=False)

    if output:
        output_path = Path(output)
        output_path.write_text(content)
        click.echo(f"Org-chart exported to {output_path}")
    else:
        click.echo(content)


# Default command - show tree when running "qn org chart" without subcommand
@chart_cmd.command("tree", hidden=True)
@pass_context
def chart_tree_alias(ctx: Context):
    """Alias for 'qn org chart show'."""
    ctx.invoke(chart_show)

"""
qn wrkr ship command.

Sanctioned worker flow to land a bead's work: branch -> commit -> push -> PR,
run from the worker's current directory (the app subtree in a monorepo).
"""

from pathlib import Path

import click

from cli.commands.context import Context, pass_context
from cli.core.constants import GIT_DEFAULT_BASE, GIT_DEFAULT_REMOTE
from cli.core.git_pr import GitError, ship_bead


@click.command("ship")
@click.option(
    "--bead",
    "bead_id",
    required=True,
    help="Bead ID this work serves (drives the branch name + commit reference).",
)
@click.option(
    "--title",
    required=True,
    help="Title for the branch slug, commit message, and PR.",
)
@click.option(
    "--base",
    default=GIT_DEFAULT_BASE,
    show_default=True,
    help="PR base branch.",
)
@click.option(
    "--remote",
    default=GIT_DEFAULT_REMOTE,
    show_default=True,
    help="Configured remote NAME to push to (not a URL).",
)
@click.option(
    "--body",
    default=None,
    help="PR body (defaults to the commit message).",
)
@click.option(
    "--no-pr",
    "no_pr",
    is_flag=True,
    default=False,
    help="Skip opening a PR (branch + push only).",
)
@pass_context
def ship_cmd(
    ctx: Context,
    bead_id: str,
    title: str,
    base: str,
    remote: str,
    body: str,
    no_pr: bool,
) -> None:
    """Branch, commit, push, and open a PR for a bead — from your current dir.

    \b
    Examples:
      qn wrkr ship --bead quinn-ai-abc --title "Add login form"
      qn wrkr ship --bead quinn-ai-abc --title "WIP" --no-pr
    """
    repo = Path.cwd()
    try:
        result = ship_bead(
            repo,
            bead_id,
            title,
            base=base,
            remote=remote,
            body=body,
            create_pr=not no_pr,
        )
    except GitError as e:
        raise click.ClickException(str(e))

    click.echo(f"Branch:    {result.branch}")
    click.echo(f"Committed: {result.committed}")
    click.echo(f"Pushed:    {result.pushed} (remote: {remote})")
    if result.pr_url:
        click.echo(f"PR:        {result.pr_url}")
    for warning in result.warnings:
        click.echo(f"Warning: {warning}", err=True)

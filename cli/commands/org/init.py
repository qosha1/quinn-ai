"""
qn org init command.
"""

import json
from pathlib import Path
from typing import List, Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.org_init import OrgInitConfig, ObjectiveConfig, init_org


# Maximum number of OKRs to collect during interactive prompting
MAX_INTERACTIVE_OKRS = 3


def _load_okrs_from_file(file_path: Path) -> List[ObjectiveConfig]:
    """Load OKRs from a JSON file.

    Args:
        file_path: Path to JSON file containing OKRs

    Returns:
        List of ObjectiveConfig objects

    Raises:
        click.ClickException: If file doesn't exist or has invalid JSON
    """
    if not file_path.exists():
        raise click.ClickException(f"OKRs file not found: {file_path}")

    try:
        content = file_path.read_text()
        okrs_data = json.loads(content)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON in OKRs file: {e}")

    if not isinstance(okrs_data, list):
        raise click.ClickException("OKRs file must contain a JSON array of objectives")

    objectives = []
    for okr in okrs_data:
        if not isinstance(okr, dict) or "title" not in okr:
            raise click.ClickException("Each OKR must have at least a 'title' field")

        from cli.core.org_init import KeyResultConfig

        key_results = []
        for kr in okr.get("key_results", []):
            key_results.append(KeyResultConfig(
                metric=kr.get("metric", ""),
                target=float(kr.get("target", 0)),
                unit=kr.get("unit", ""),
            ))

        objectives.append(ObjectiveConfig(
            title=okr["title"],
            key_results=key_results,
        ))

    return objectives


def _prompt_for_okrs() -> List[ObjectiveConfig]:
    """Interactively prompt user for OKRs.

    Returns:
        List of ObjectiveConfig objects (empty if user skips)
    """
    click.echo("")
    click.echo("Define your organization's objectives (OKRs).")
    click.echo("Press Enter without text to skip and use default bootstrap OKR.")
    click.echo("")

    objectives = []

    for i in range(MAX_INTERACTIVE_OKRS):
        prompt_text = f"Objective {i + 1}" if i == 0 else f"Objective {i + 1} (optional)"
        title = click.prompt(
            prompt_text,
            default="",
            show_default=False,
        ).strip()

        if not title:
            # Empty input - stop collecting
            break

        objectives.append(ObjectiveConfig(title=title))

        # Ask for more if we haven't reached the max
        if i < MAX_INTERACTIVE_OKRS - 1:
            if not click.confirm("Add another objective?", default=False):
                break

    return objectives


@click.command()
@click.option(
    "--ceo-name",
    default="CEO",
    help="Name for the CEO worker.",
)
@click.option(
    "--okrs-file",
    type=click.Path(exists=False),
    default=None,
    help="Path to JSON file with initial OKRs.",
)
@click.option(
    "--skip-okrs",
    is_flag=True,
    default=False,
    help="Skip OKR prompting and use bootstrap OKR.",
)
@pass_context
def init_cmd(
    ctx: Context,
    ceo_name: str,
    okrs_file: Optional[str],
    skip_okrs: bool,
):
    """Initialize a new organization.

    Creates the org folder structure, copies default config templates,
    initializes the database, and creates the CEO worker.

    OKRs (Objectives and Key Results) can be provided in three ways:
    1. Interactive prompting (default): You'll be asked to enter objectives
    2. File import (--okrs-file): Load from a JSON file
    3. Skip (--skip-okrs): Use a generic bootstrap OKR

    Example OKRs file format:
    [
      {"title": "Launch MVP", "key_results": [{"metric": "features", "target": 5}]},
      {"title": "Build team", "key_results": [{"metric": "engineers", "target": 3}]}
    ]
    """
    org_path = ctx.org_path

    # Determine objectives
    objectives: List[ObjectiveConfig] = []

    if okrs_file:
        # Load from file
        objectives = _load_okrs_from_file(Path(okrs_file))
        click.echo(f"Loaded {len(objectives)} objective(s) from {okrs_file}")
    elif not skip_okrs:
        # Try interactive prompting - falls back gracefully if no input available
        try:
            objectives = _prompt_for_okrs()
            if objectives:
                click.echo(f"Collected {len(objectives)} objective(s)")
        except click.exceptions.Abort:
            # User aborted or no input available - use bootstrap OKR
            objectives = []

    # Create config for initialization
    config = OrgInitConfig(
        path=org_path,
        name=org_path.name,
        ceo_name=ceo_name,
        ceo_role="CEO",  # Always CEO
        objectives=objectives,
    )

    # Initialize the org
    result = init_org(config)

    if not result.success:
        raise click.ClickException(result.error or "Failed to initialize organization")

    click.echo(f"Initialized organization at {result.org_path}")
    click.echo(f"Created CEO: {result.ceo_name}")
    click.echo(f"Database: {result.db_path}")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  1. Configure providers in config/providers.yaml")
    click.echo("  2. Run 'qn org start' to start the organization")

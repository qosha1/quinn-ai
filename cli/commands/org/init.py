"""
qn org init command.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.org_init import OrgInitConfig, ObjectiveConfig, init_org


# Maximum number of OKRs to collect during interactive prompting
MAX_INTERACTIVE_OKRS = 3

# Sentinel: --ceo-name not provided. We use this instead of literal "CEO"
# so we can detect the unset case and either prompt or fail with a clear
# message. (See quinn-ai-i78p.)
_CEO_NAME_UNSET = "__CEO_NAME_UNSET__"


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
    # Header goes to stderr so it doesn't interleave with stdout success
    # output when stdin is non-TTY and the prompt EOFs immediately
    # (quinn-ai-udlo). The prompt itself is also on stderr (click default).
    click.echo("", err=True)
    click.echo("Define your organization's objectives (OKRs).", err=True)
    click.echo("Press Enter without text to skip and use default bootstrap OKR.", err=True)
    click.echo("", err=True)

    objectives = []

    for i in range(MAX_INTERACTIVE_OKRS):
        prompt_text = f"Objective {i + 1}" if i == 0 else f"Objective {i + 1} (optional)"
        # err=True keeps the prompt off stdout so scripts that capture
        # stdout don't see "Objective 1:" interleaved with success output.
        title = click.prompt(
            prompt_text,
            default="",
            show_default=False,
            err=True,
        ).strip()

        if not title:
            # Empty input - stop collecting
            break

        objectives.append(ObjectiveConfig(title=title))

        # Ask for more if we haven't reached the max
        if i < MAX_INTERACTIVE_OKRS - 1:
            if not click.confirm("Add another objective?", default=False, err=True):
                break

    return objectives


@click.command()
@click.option(
    "--ceo-name",
    default=_CEO_NAME_UNSET,
    help="Name for the CEO worker. Required in non-interactive contexts.",
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
@click.option(
    "--reuse-beads",
    is_flag=True,
    default=False,
    help=(
        "Deliberately share an existing .beads/ tracker at the target path "
        "instead of erroring. Default is to refuse — most cases of "
        "'.beads/ already exists' mean the target dir belongs to another "
        "project (e.g. you're inside a git repo whose root has its own "
        "tracker), and sharing pollutes that project's beads. Pass this "
        "flag only if you know the existing .beads/ is yours to extend."
    ),
)
@click.option(
    "--host/--no-host",
    "host_mode_flag",
    default=None,
    help=(
        "Host mode: overlay the org onto an existing project. Org metadata "
        "lands under <path>/.quinnai/; project's existing .beads/ is reused; "
        "root files (CLAUDE.md, README.md, AGENTS.md) are not created or "
        "overwritten. Auto-detected when .beads/ or .git/ exists at the "
        "target path. Use --no-host to force greenfield."
    ),
)
@pass_context
def init_cmd(
    ctx: Context,
    ceo_name: str,
    okrs_file: Optional[str],
    skip_okrs: bool,
    reuse_beads: bool,
    host_mode_flag: Optional[bool],
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
    # init is special: the org doesn't exist yet, so the usual auto-discovery
    # (walk up looking for live/quinn.db) can't help. Fall back to cwd —
    # mirrors `git init` semantics.
    org_path = ctx.org_path or Path.cwd()

    # Resolve host mode (host-mode-init):
    #   --host         → True (explicit)
    #   --no-host      → False (explicit greenfield)
    #   neither passed → auto-detect: True iff .beads/ or .git/ exists.
    if host_mode_flag is None:
        host_mode = (
            (org_path / ".beads").exists() or (org_path / ".git").exists()
        )
        if host_mode:
            click.echo(
                f"Host mode auto-detected at {org_path} (existing .beads/ or "
                f".git/ found). Org metadata will land under .quinnai/. Use "
                f"--no-host to force greenfield.",
            )
    else:
        host_mode = host_mode_flag

    is_tty = sys.stdin.isatty()

    # Resolve --ceo-name. If unset and we have a TTY, prompt. If unset and
    # no TTY, fall back to "CEO" but warn loudly so the placeholder isn't
    # silent (quinn-ai-i78p).
    if ceo_name == _CEO_NAME_UNSET:
        if is_tty:
            ceo_name = click.prompt("CEO name", default="CEO", err=True)
        else:
            click.echo(
                "Warning: --ceo-name not provided; using placeholder 'CEO'. "
                "Set explicitly with --ceo-name=\"<name>\" or rename later.",
                err=True,
            )
            ceo_name = "CEO"

    # Determine objectives
    objectives: List[ObjectiveConfig] = []

    if okrs_file:
        # Load from file
        objectives = _load_okrs_from_file(Path(okrs_file))
        click.echo(f"Loaded {len(objectives)} objective(s) from {okrs_file}")
    elif not skip_okrs:
        try:
            objectives = _prompt_for_okrs()
            if objectives:
                click.echo(f"Collected {len(objectives)} objective(s)")
        except click.exceptions.Abort:
            # Non-TTY EOF or user-aborted: fall through to bootstrap OKR
            objectives = []

    # Create config for initialization
    config = OrgInitConfig(
        path=org_path,
        name=org_path.name,
        ceo_name=ceo_name,
        ceo_role="CEO",  # Always CEO
        objectives=objectives,
        reuse_beads=reuse_beads,
        skip_okrs=skip_okrs,
        host_mode=host_mode,
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

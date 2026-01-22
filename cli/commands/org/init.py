"""
qn org init command.
"""

from pathlib import Path

import click

from commands.main import pass_context, Context
from core.db import init_database, get_org_db_path
from core.org import Org


@click.command()
@click.option(
    "--ceo-name",
    default="CEO",
    help="Name for the CEO worker.",
)
@click.option(
    "--ceo-role",
    default="CEO",
    help="Role title for the CEO.",
)
@pass_context
def init_cmd(ctx: Context, ceo_name: str, ceo_role: str):
    """Initialize a new organization.

    Creates the org folder structure, initializes the database,
    and creates the CEO worker.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    # Check if already initialized
    if db_path.exists():
        raise click.ClickException(
            f"Organization already initialized at {org_path}"
        )

    # Create folder structure
    _create_folder_structure(org_path)

    # Initialize database
    db = init_database(db_path)

    try:
        # Initialize org with CEO
        org = Org(db)
        ceo = org.init(ceo_name, ceo_role)

        click.echo(f"Initialized organization at {org_path}")
        click.echo(f"Created CEO: {ceo.name} ({ceo.role})")
        click.echo(f"Database: {db_path}")
        click.echo("")
        click.echo("Next steps:")
        click.echo("  qn org start    Start the organization")

    finally:
        db.close()


def _create_folder_structure(org_path: Path) -> None:
    """Create the org folder structure.

    Structure:
        org_path/
        ├── live/           # Runtime data (quinn.db, logs)
        ├── shared/         # Shared knowledge (topics, team docs)
        └── workers/        # Per-worker storage (mirrors org-chart)
    """
    # Create main directories
    (org_path / "live").mkdir(parents=True, exist_ok=True)
    (org_path / "shared").mkdir(parents=True, exist_ok=True)
    (org_path / "workers").mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (org_path / "shared" / "topics").mkdir(exist_ok=True)
    (org_path / "shared" / "teams").mkdir(exist_ok=True)

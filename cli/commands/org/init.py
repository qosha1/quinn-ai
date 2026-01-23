"""
qn org init command.
"""

import shutil
from pathlib import Path
from importlib import resources

import click

from cli.commands.context import pass_context, Context
from cli.core.db import init_database, get_org_db_path
from cli.core.org import Org


def _get_config_template_path() -> Path:
    """Get path to config templates using importlib.resources.

    Falls back to __file__-based path if resources are not available.
    This supports both development (editable install) and packaged installs.

    Returns:
        Path to the config templates directory
    """
    try:
        # Use importlib.resources for proper package data access
        # This works in packaged distributions and zip imports
        with resources.as_file(resources.files("cli.config")) as config_path:
            return config_path
    except (TypeError, ModuleNotFoundError):
        # Fallback for development: use source-relative path
        return Path(__file__).parent.parent.parent / "config"


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

    Creates the org folder structure, copies default config templates,
    initializes the database, and creates the CEO worker.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    # Check if already initialized
    if db_path.exists():
        raise click.ClickException(
            f"Organization already initialized at '{org_path}'.\n"
            "Run 'qn org status' to view or 'qn org start' to start it."
        )

    # Create folder structure
    _create_folder_structure(org_path)

    # Copy default config templates
    _copy_default_configs(org_path)

    # Initialize database
    db = init_database(db_path)

    try:
        # Initialize org with CEO
        org = Org(db)
        ceo = org.init(ceo_name, ceo_role)

        # Create initial org-chart
        _create_org_chart(org_path, ceo)

        click.echo(f"Initialized organization at {org_path}")
        click.echo(f"Created CEO: {ceo.name} ({ceo.role})")
        click.echo(f"Database: {db_path}")
        click.echo("")
        click.echo("Next steps:")
        click.echo("  1. Configure providers in config/providers.yaml")
        click.echo("  2. Run 'qn org start' to start the organization")

    finally:
        db.close()


def _create_folder_structure(org_path: Path) -> None:
    """Create the org folder structure.

    Structure per README spec:
        org_path/
        ├── config/             # Org config (providers, templates)
        ├── org-chart/          # Git-tracked hiring decisions output
        ├── live/               # Runtime state
        │   ├── quinn.db
        │   └── workers/        # Per-worker session state
        └── storage/            # Abstracted storage
            ├── shared/         # Org lifetime (topics, teams)
            └── workers/        # Worker lifetime (mirrors org-chart)
    """
    # Config directory
    (org_path / "config").mkdir(parents=True, exist_ok=True)

    # Org-chart output directory
    (org_path / "org-chart").mkdir(parents=True, exist_ok=True)

    # Runtime state
    (org_path / "live").mkdir(parents=True, exist_ok=True)
    (org_path / "live" / "workers").mkdir(exist_ok=True)

    # Storage directories
    (org_path / "storage" / "shared").mkdir(parents=True, exist_ok=True)
    (org_path / "storage" / "workers").mkdir(parents=True, exist_ok=True)


def _copy_default_configs(org_path: Path) -> None:
    """Copy default config templates to org config directory.

    Copies providers.yaml and worker-templates.yaml from package defaults.
    """
    config_dir = org_path / "config"

    # Copy providers.yaml
    providers_src = _get_config_template_path() / "providers.yaml"
    if providers_src.exists():
        shutil.copy(providers_src, config_dir / "providers.yaml")

    # Copy worker-templates.yaml
    templates_src = _get_config_template_path() / "worker-templates.yaml"
    if templates_src.exists():
        shutil.copy(templates_src, config_dir / "worker-templates.yaml")


def _create_org_chart(org_path: Path, ceo) -> None:
    """Create initial org-chart file.

    The org-chart is the git-tracked output of hiring decisions.
    """
    import yaml

    org_chart = {
        "version": "1.0",
        "workers": {
            ceo.id: {
                "name": ceo.name,
                "role": ceo.role,
                "lifecycle": ceo.lifecycle_status,
                "manager": None,
                "reports": [],
            }
        },
        "hierarchy": {
            "root": ceo.id,
        }
    }

    chart_path = org_path / "org-chart" / "current.yaml"
    with open(chart_path, "w") as f:
        yaml.dump(org_chart, f, default_flow_style=False, sort_keys=False)

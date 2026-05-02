"""qn org env — show environment variables injected into worker sessions."""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.queries import resolve_worker
from cli.core.onboarding import load_onboarding_context, get_worker_env_vars
from cli.core.storage import StorageManager
from cli.core.constants import SHARED_DIR, STORAGE_DIR


@click.command("env")
@click.option("--worker", default=None, help="Show env for a specific worker (name or ID).")
@pass_context
def env_cmd(ctx: Context, worker: str) -> None:
    """Show environment variables injected into worker sessions at spawn time."""
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        org = Org.load(db)

        if worker:
            target = resolve_worker(db, worker)
            if not target:
                raise click.ClickException(f"Worker '{worker}' not found.")
            worker_id = target.id
        else:
            if not org.ceo:
                raise click.ClickException("No CEO found.")
            worker_id = org.ceo.id

        ctx_obj = load_onboarding_context(db, worker_id, org_path)
        env = get_worker_env_vars(ctx_obj, org_path, db)

        click.echo(f"Environment variables for worker {worker_id}:\n")
        for key in sorted(env):
            click.echo(f"  {key}={env[key]}")
    finally:
        db.close()

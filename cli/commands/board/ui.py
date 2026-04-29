"""
Board UI command.

Launches the browser-based board UI for organization oversight.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import click

from cli.commands.context import pass_context


BOARD_UI_DIR = Path(__file__).parent.parent.parent.parent / "board_ui_web"
DEFAULT_PORT = 7842


@click.command()
@click.option(
    "--org-path",
    "-o",
    type=click.Path(exists=True, path_type=Path),
    help="Path to org folder to monitor",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=DEFAULT_PORT,
    help=f"Port for the web UI (default: {DEFAULT_PORT})",
)
@click.option(
    "--no-open",
    is_flag=True,
    default=False,
    help="Don't open browser automatically",
)
@pass_context
def ui_cmd(ctx, org_path: Path | None, port: int, no_open: bool) -> None:
    """Launch the board web UI.

    Opens a browser-based dashboard for monitoring and managing AI organizations.

    \b
    Examples:
        qn board ui                       # Auto-detect org from current dir
        qn board ui -o ~/my-org           # Connect to specific org
        qn board ui --port 8080           # Use custom port
        qn board ui --no-open             # Start server without opening browser
    """
    if not BOARD_UI_DIR.exists():
        click.echo(f"Error: Board UI not found at {BOARD_UI_DIR}", err=True)
        raise click.Abort()

    node_modules = BOARD_UI_DIR / "node_modules"
    if not node_modules.exists():
        click.echo("Installing board UI dependencies…")
        subprocess.run(["npm", "install", "--silent"], cwd=BOARD_UI_DIR, check=True)

    next_build = BOARD_UI_DIR / ".next"
    if not next_build.exists():
        click.echo("Building board UI (first run, takes ~20s)…")
        subprocess.run(["npm", "run", "build"], cwd=BOARD_UI_DIR, check=True)

    resolved_org = _resolve_org_path(org_path, ctx)
    db_path = resolved_org / "live" / "quinn.db" if resolved_org else None

    env = os.environ.copy()
    if db_path and db_path.exists():
        env["QUINN_DB_PATH"] = str(db_path)
        env["QUINN_ORG_PATH"] = str(resolved_org)
        click.echo(f"Connected to org: {resolved_org.name} ({db_path})")
    else:
        click.echo("Warning: No org database found. Dashboard will show errors until org is initialized.")

    url = f"http://localhost:{port}"
    click.echo(f"Starting QuinnAI Board at {url}")

    proc = subprocess.Popen(
        ["npm", "start", "--", "--port", str(port)],
        cwd=BOARD_UI_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for server to start
    if not _wait_for_server(url, timeout=15):
        click.echo("Error: Server failed to start within 15 seconds", err=True)
        proc.terminate()
        sys.exit(1)

    if not no_open:
        click.launch(url)

    click.echo(f"Board UI running at {url} (Ctrl+C to stop)")
    try:
        proc.wait()
    except KeyboardInterrupt:
        click.echo("\nStopping board UI…")
        proc.terminate()


def _resolve_org_path(org_path: Path | None, ctx) -> Path | None:
    if org_path:
        return org_path
    if ctx and ctx.org_path:
        return ctx.org_path
    cwd = Path.cwd()
    if (cwd / "live" / "quinn.db").exists():
        return cwd
    return None


def _wait_for_server(url: str, timeout: int = 15) -> bool:
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{url}/api/org", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False

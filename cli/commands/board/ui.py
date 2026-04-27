"""
Board TUI command.

Launches the interactive board terminal UI for organization oversight.
"""

from pathlib import Path
from typing import Optional

import click

from cli.commands.context import pass_context


@click.command()
@click.option(
    "--org-path",
    "-o",
    type=click.Path(exists=True, path_type=Path),
    multiple=True,
    help="Path to org folder(s) to monitor",
)
@click.option(
    "--terminal",
    "-t",
    type=click.Choice(["kitty", "iterm", "terminal", "auto"]),
    default="auto",
    help="Preferred terminal emulator for chat windows",
)
@pass_context
def ui_cmd(ctx, org_path: tuple[Path, ...], terminal: str) -> None:
    """Launch the board terminal UI.

    Interactive dashboard for monitoring and managing AI organizations.

    \b
    Examples:
        qn board ui                       # Auto-detect orgs in current dir
        qn board ui -o ~/my-org           # Connect to specific org
        qn board ui -o ~/org1 -o ~/org2   # Monitor multiple orgs
        qn board ui --terminal kitty      # Use Kitty for chat windows
    """
    try:
        from board_ui.app import BoardApp
        from board_ui.config import BoardConfig
        from board_ui.interfaces.terminal import TerminalType
    except ImportError as e:
        click.echo(
            "Error: Board UI not installed. "
            "Install with: pip install quinnai-board",
            err=True,
        )
        raise click.Abort() from e

    # Build configuration
    config = BoardConfig(
        org_paths=list(org_path) if org_path else [],
        preferred_terminal=_parse_terminal(terminal),
    )

    # If no org paths specified, use default search paths
    if not config.org_paths:
        # Use context org_path if available
        if ctx.org_path:
            config.org_paths = [ctx.org_path]
        else:
            # Fall back to default search paths
            cwd = Path.cwd()
            default_orgs_dir = Path.home() / "orgs"
            config.org_paths = [default_orgs_dir, cwd]

    # Launch the app
    app = BoardApp(config)
    app.run()


def _parse_terminal(terminal: str) -> Optional["TerminalType"]:
    """Parse terminal choice to TerminalType."""
    try:
        from board_ui.interfaces.terminal import TerminalType
    except ImportError:
        return None

    if terminal == "auto":
        return None
    elif terminal == "kitty":
        return TerminalType.KITTY
    elif terminal == "iterm":
        return TerminalType.ITERM2
    elif terminal == "terminal":
        return TerminalType.MACOS_TERMINAL
    return None

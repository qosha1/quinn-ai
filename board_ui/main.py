"""
Board UI entry point.

DEPRECATED: Use `qn board ui` instead of `qn-board`.

This entry point is maintained for backward compatibility but will be removed
in a future version. The board TUI is now integrated with the main qn CLI.
"""

import sys
from pathlib import Path
from typing import Optional

import click

from .app import BoardApp
from .config import BoardConfig
from .interfaces.terminal import TerminalType


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
@click.version_option()
def main(
    org_path: tuple[Path, ...],
    terminal: str,
) -> None:
    """QuinnAI Board - Interactive oversight for AI organizations.

    DEPRECATED: Use `qn board ui` instead.

    Launch the board terminal UI to monitor and interact with running orgs.

    \b
    Examples:
        qn board ui                       # Auto-detect orgs in current dir
        qn board ui -o ~/my-org           # Connect to specific org
        qn board ui -o ~/org1 -o ~/org2   # Monitor multiple orgs
        qn board ui --terminal kitty      # Use Kitty for chat windows
    """
    # Show deprecation warning
    click.echo(
        "Warning: 'qn-board' is deprecated. Use 'qn board ui' instead.",
        err=True,
    )
    click.echo("", err=True)
    # Build configuration
    config = BoardConfig(
        org_paths=list(org_path) if org_path else [],
        preferred_terminal=_parse_terminal(terminal),
    )

    # If no org paths specified, use default search paths
    if not config.org_paths:
        cwd = Path.cwd()
        # Always provide search paths even if they don't exist yet
        default_orgs_dir = Path.home() / "orgs"
        config.org_paths = [default_orgs_dir, cwd]

    # Launch the app
    app = BoardApp(config)
    app.run()


def _parse_terminal(terminal: str) -> Optional[TerminalType]:
    """Parse terminal choice to TerminalType."""
    if terminal == "auto":
        return None
    elif terminal == "kitty":
        return TerminalType.KITTY
    elif terminal == "iterm":
        return TerminalType.ITERM2
    elif terminal == "terminal":
        return TerminalType.MACOS_TERMINAL
    return None


if __name__ == "__main__":
    main()

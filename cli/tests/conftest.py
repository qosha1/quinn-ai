"""
Pytest configuration for CLI tests.
"""

# No sys.path manipulation needed - packages are installed via pyproject.toml
# Tests should be run from the quinnai directory with: pytest cli/tests/
# Or with the package installed: pip install -e . && pytest

# Auto-skip @pytest.mark.tmux tests when tmux is not available, and expose
# the tmux_with_fake_cli fixture for any test that opts in.
from cli.tests.harness.tmux_fixtures import (  # noqa: E402, F401
    pytest_collection_modifyitems,
    tmux_with_fake_cli,
)

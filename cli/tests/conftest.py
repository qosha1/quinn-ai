"""
Pytest configuration for CLI tests.
"""

import sys
from pathlib import Path

# Add cli to Python path
cli_path = Path(__file__).parent.parent
sys.path.insert(0, str(cli_path))

# Add project root to Python path (for shared/)
project_root = cli_path.parent
sys.path.insert(0, str(project_root))

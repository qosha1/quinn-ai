"""
Pytest configuration for CLI tests.
"""

import sys
from pathlib import Path

# Add cli to Python path
cli_path = Path(__file__).parent.parent
sys.path.insert(0, str(cli_path))

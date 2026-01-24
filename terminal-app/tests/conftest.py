"""Pytest configuration for board UI tests."""

import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Add parent directory (quinnai) to path for shared module imports
quinnai_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(quinnai_path))

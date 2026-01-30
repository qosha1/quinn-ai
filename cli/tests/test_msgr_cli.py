"""Tests for msgr CLI entry point."""

import subprocess
import sys
from pathlib import Path


def test_msgr_help():
    """Test that msgr --help works."""
    # Run msgr --help via Python module
    result = subprocess.run(
        [sys.executable, "-m", "msgr.main", "--help"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "msgr - QuinnAI messaging CLI" in result.stdout
    assert "msgr inbox" in result.stdout
    assert "msgr send" in result.stdout
    assert "msgr channels" in result.stdout


def test_msgr_version():
    """Test that msgr package can be imported."""
    import msgr

    assert hasattr(msgr, "__version__")
    assert msgr.__version__ == "0.1.0"

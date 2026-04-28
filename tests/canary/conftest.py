"""Canary test gating + spec discovery."""
import os
from pathlib import Path

import pytest

CANARY_ENABLED = os.environ.get("QUINNAI_RUN_CANARY", "0") == "1"
SPECS_DIR = Path(__file__).parent / "specs"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "canary: marks tests as live-LLM canaries (skipped unless QUINNAI_RUN_CANARY=1)"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests bearing the explicit @pytest.mark.canary marker.

    NOTE: item.keywords includes path components, so 'tests/canary/...' would
    match every item under that tree. Use get_closest_marker to only target
    items that genuinely declared the marker.
    """
    if CANARY_ENABLED:
        return
    skip_canary = pytest.mark.skip(reason="canary disabled (set QUINNAI_RUN_CANARY=1 to enable)")
    for item in items:
        if item.get_closest_marker("canary") is not None:
            item.add_marker(skip_canary)


def pytest_generate_tests(metafunc):
    if "canary_spec_path" in metafunc.fixturenames:
        specs = sorted(SPECS_DIR.glob("*.yml"))
        ids = [p.stem for p in specs]
        metafunc.parametrize("canary_spec_path", specs, ids=ids)

"""Clipboard + scratchpad exporter.

Tries the system clipboard (pbcopy on macOS, xclip on Linux); on failure or
when no clipboard is available, writes to a timestamped file under the org's
exports/ directory (or the OS temp dir as a last resort).
"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional


class ClipboardExporter:
    """Copy text to system clipboard or fall back to a scratchpad file."""

    def __init__(self, org_path: Optional[Path] = None) -> None:
        """Args:
        org_path: When set, scratchpad files land in {org_path}/exports/. When
            None (no org connected), they land in {tempdir}/quinnai_exports/.
        """
        self._org_path = org_path

    def copy(self, text: str) -> bool:
        """Copy text to system clipboard. Returns True on success."""
        for cmd in (["pbcopy"], ["xclip", "-selection", "clipboard"]):
            try:
                subprocess.run(
                    cmd,
                    input=text.encode("utf-8"),
                    check=True,
                    capture_output=True,
                    timeout=2,
                )
                return True
            except (
                FileNotFoundError,
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
            ):
                continue
        return False

    def write_to_scratchpad(self, content: str, view_name: str) -> Path:
        """Write content to a timestamped file. Returns the file path."""
        if self._org_path:
            export_dir = self._org_path / "exports"
        else:
            export_dir = Path(tempfile.gettempdir()) / "quinnai_exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = export_dir / f"board_{view_name}_{timestamp}.txt"
        filepath.write_text(content, encoding="utf-8")
        return filepath

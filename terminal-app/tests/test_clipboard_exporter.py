"""Direct unit tests for ClipboardExporter (no BoardApp needed)."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from board_ui.services.clipboard_exporter import ClipboardExporter


class TestCopy:
    def test_copy_succeeds_when_pbcopy_available(self):
        exporter = ClipboardExporter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = None  # success
            assert exporter.copy("hello") is True
        # Should have tried pbcopy first
        cmd_args = mock_run.call_args_list[0].args[0]
        assert cmd_args == ["pbcopy"]

    def test_copy_falls_through_pbcopy_to_xclip(self):
        exporter = ClipboardExporter()

        def fake_run(cmd, **kwargs):
            if cmd[0] == "pbcopy":
                raise FileNotFoundError()
            return None  # xclip succeeds

        with patch("subprocess.run", side_effect=fake_run) as mock_run:
            assert exporter.copy("hello") is True
        assert [c.args[0][0] for c in mock_run.call_args_list] == ["pbcopy", "xclip"]

    def test_copy_returns_false_when_no_clipboard_available(self):
        exporter = ClipboardExporter()
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert exporter.copy("hello") is False

    def test_copy_handles_called_process_error(self):
        exporter = ClipboardExporter()
        err = subprocess.CalledProcessError(1, "pbcopy")
        with patch("subprocess.run", side_effect=err):
            assert exporter.copy("hello") is False


class TestWriteToScratchpad:
    def test_writes_under_org_exports_when_org_path_set(self, tmp_path: Path):
        exporter = ClipboardExporter(org_path=tmp_path)
        result = exporter.write_to_scratchpad("body", "dashboard")
        assert result.parent == tmp_path / "exports"
        assert result.read_text() == "body"
        assert result.name.startswith("board_dashboard_")
        assert result.name.endswith(".txt")

    def test_creates_exports_directory_if_missing(self, tmp_path: Path):
        target = tmp_path / "no-dir-yet"
        exporter = ClipboardExporter(org_path=target)
        result = exporter.write_to_scratchpad("body", "team")
        assert result.parent.exists()

    def test_falls_back_to_tempdir_when_no_org_path(self):
        exporter = ClipboardExporter(org_path=None)
        result = exporter.write_to_scratchpad("body", "logs")
        assert result.parent.name == "quinnai_exports"
        assert result.parent.parent == Path(tempfile.gettempdir())
        assert result.read_text() == "body"
        result.unlink()  # cleanup

    def test_filename_includes_view_name_and_timestamp(self, tmp_path: Path):
        exporter = ClipboardExporter(org_path=tmp_path)
        result = exporter.write_to_scratchpad("x", "messages")
        # Format: board_{view}_{YYYYMMDD_HHMMSS}.txt
        assert result.name.startswith("board_messages_")
        # 8 digits date + _ + 6 digits time + .txt → 19 chars after prefix
        suffix = result.name[len("board_messages_"):]
        assert len(suffix) == len("YYYYMMDD_HHMMSS.txt")

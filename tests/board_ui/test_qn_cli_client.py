"""Direct unit tests for QnCliClient."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from board_ui.services import qn_cli_client
from board_ui.services.qn_cli_client import (
    CommandResult,
    QnCliClient,
    get_default_qn_cli,
    reset_default_qn_cli_for_tests,
)


@pytest.fixture(autouse=True)
def reset_default_singleton():
    reset_default_qn_cli_for_tests()
    yield
    reset_default_qn_cli_for_tests()


class TestRunSuccess:
    def test_run_returns_success_on_zero_exit(self):
        client = QnCliClient(command=["fake-qn"])
        cp = MagicMock(returncode=0, stdout="ok\n", stderr="")
        with patch("subprocess.run", return_value=cp):
            result = client.run(["org", "status"])
        assert result.success is True
        assert result.returncode == 0
        assert result.stdout == "ok\n"
        assert result.error_message == ""
        assert result.timed_out is False

    def test_run_passes_args_after_command_prefix(self):
        client = QnCliClient(command=["/usr/bin/qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.run(["org", "start", "--provider", "claude_code"])
        called_args = m.call_args.args[0]
        assert called_args == ["/usr/bin/qn", "org", "start", "--provider", "claude_code"]

    def test_run_passes_cwd_when_given(self, tmp_path: Path):
        client = QnCliClient(command=["fake-qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.run(["x"], cwd=tmp_path)
        assert m.call_args.kwargs["cwd"] == str(tmp_path)


class TestRunFailures:
    def test_run_returns_failure_on_nonzero_with_stderr_message(self):
        client = QnCliClient(command=["fake-qn"])
        cp = MagicMock(returncode=2, stdout="", stderr="boom\n")
        with patch("subprocess.run", return_value=cp):
            result = client.run(["org", "status"])
        assert result.success is False
        assert result.returncode == 2
        assert result.error_message == "boom"

    def test_run_uses_stdout_when_stderr_empty(self):
        client = QnCliClient(command=["fake-qn"])
        cp = MagicMock(returncode=2, stdout="usage: qn ...\n", stderr="")
        with patch("subprocess.run", return_value=cp):
            result = client.run(["foo"])
        assert result.error_message == "usage: qn ..."

    def test_run_handles_timeout_expired(self):
        client = QnCliClient(command=["fake-qn"])
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="qn", timeout=5)):
            result = client.run(["x"], timeout=5)
        assert result.success is False
        assert result.timed_out is True
        assert "timed out" in result.error_message.lower()

    def test_run_handles_file_not_found(self):
        client = QnCliClient(command=["/nope/qn"])
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = client.run(["x"])
        assert result.success is False
        assert "not found" in result.error_message.lower()
        assert "/nope/qn" in result.error_message

    def test_run_handles_unexpected_exception(self):
        client = QnCliClient(command=["fake-qn"])
        with patch("subprocess.run", side_effect=RuntimeError("weird")):
            result = client.run(["x"])
        assert result.success is False
        assert "weird" in result.error_message


class TestAvailable:
    def test_available_true_when_help_succeeds(self):
        client = QnCliClient(command=["fake-qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="usage", stderr="")):
            ok, msg = client.available()
        assert ok is True
        assert msg == ""

    def test_available_false_when_qn_missing(self):
        client = QnCliClient(command=["/missing/qn"])
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            ok, msg = client.available()
        assert ok is False
        assert "not found" in msg.lower()


class TestConvenienceHelpers:
    def test_org_start_includes_skip_validation_for_claude_code(self):
        client = QnCliClient(command=["qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.org_start(Path("/x"), provider="claude_code")
        args = m.call_args.args[0]
        assert "--skip-config-validation" in args
        assert "--provider" in args
        assert "claude_code" in args

    def test_org_start_does_not_skip_validation_for_other_providers_unless_asked(self):
        client = QnCliClient(command=["qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.org_start(Path("/x"), provider="cursor")
        args = m.call_args.args[0]
        assert "--skip-config-validation" not in args

    def test_org_start_no_spawn_ceo_omits_provider(self):
        client = QnCliClient(command=["qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.org_start(Path("/x"), spawn_ceo=False)
        args = m.call_args.args[0]
        assert "--no-spawn-ceo" in args
        assert "--provider" not in args

    def test_org_stop_includes_yes_flag(self):
        client = QnCliClient(command=["qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.org_stop(Path("/x"))
        args = m.call_args.args[0]
        assert "--yes" in args
        assert "stop" in args

    def test_org_stop_passes_force_and_no_cleanup(self):
        client = QnCliClient(command=["qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.org_stop(Path("/x"), force=True, cleanup=False)
        args = m.call_args.args[0]
        assert "--force" in args
        assert "--no-cleanup" in args

    def test_wrkr_restart_passes_force(self):
        client = QnCliClient(command=["qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.wrkr_restart(Path("/x"), "worker-abc", force=True)
        args = m.call_args.args[0]
        assert "wrkr" in args and "restart" in args and "worker-abc" in args
        assert "--force" in args

    def test_org_provider_default_passes_provider_name(self):
        client = QnCliClient(command=["qn"])
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as m:
            client.org_provider_default(Path("/x"), "openai")
        args = m.call_args.args[0]
        assert args[-1] == "openai"
        assert "default" in args


class TestDefaultSingleton:
    def test_default_singleton_caches_instance(self):
        a = get_default_qn_cli()
        b = get_default_qn_cli()
        assert a is b

    def test_reset_clears_singleton(self):
        a = get_default_qn_cli()
        reset_default_qn_cli_for_tests()
        b = get_default_qn_cli()
        assert a is not b


class TestCommandProperty:
    def test_command_returns_copy_not_reference(self):
        client = QnCliClient(command=["qn", "--flag"])
        cmd = client.command
        cmd.append("mutated")
        # Mutation should NOT affect the client's stored command
        assert client.command == ["qn", "--flag"]

"""Contract tests for FakeSession (bead quinn-ai-yei).

FakeSession is a SessionInterface adapter that spawns instantly without
a real process. These tests verify the harness itself; tests that USE
the harness to close audit gaps live in cli/tests/test_audit_*.py.
"""

import pytest

from cli.core.session import SessionConfig, SessionInterface, SessionState
from cli.core.sessions.registry import SessionRegistry, get_default_registry

from cli.tests.harness import FakeSession, with_fake_session_registry


def _config(worker_id: str = "wrkr-test", provider: str = "fake") -> SessionConfig:
    return SessionConfig(
        worker_id=worker_id,
        provider=provider,
        command="ignored",
    )


class TestFakeSessionContract:
    def test_is_a_session_interface(self):
        sess = FakeSession(_config())
        assert isinstance(sess, SessionInterface)
        assert sess.provider_name == "fake"

    def test_start_transitions_to_running(self):
        sess = FakeSession(_config())
        sess.start()
        assert sess.state in (SessionState.STARTING, SessionState.RUNNING, SessionState.IDLE)
        assert sess.is_alive is True
        assert sess.pid == 99000

    def test_stop_terminates(self):
        sess = FakeSession(_config())
        sess.start()
        sess.stop()
        assert sess.terminate_was_called is True
        assert sess.is_alive is False

    def test_send_input_records(self):
        sess = FakeSession(_config())
        sess.start()
        sess._send_input("hello")
        sess._send_input("world")
        assert sess.inputs_sent == ["hello", "world"]

    def test_set_should_fail_spawn(self):
        sess = FakeSession(_config())
        sess.set_should_fail_spawn(True)
        with pytest.raises(Exception):
            sess.start()

    def test_factory_log_records_instances(self):
        FakeSession.reset_log()
        a = FakeSession(_config(worker_id="a"))
        b = FakeSession(_config(worker_id="b"))
        created = FakeSession.created()
        assert len(created) == 2
        assert a in created and b in created
        FakeSession.reset_log()


class TestWithFakeSessionRegistry:
    def test_swaps_default_registry_for_known_providers(self):
        # Outside the context, claude_code is the real adapter
        before = get_default_registry()
        before_class = before.get("claude_code")
        assert before_class.__name__ != "FakeSession"

        with with_fake_session_registry() as fake_cls:
            inside = get_default_registry()
            assert inside.get("fake") is FakeSession
            # Standard provider names are also intercepted by default
            assert inside.get("claude_code") is FakeSession
            assert fake_cls is FakeSession

        # After: real registry restored
        after = get_default_registry()
        assert after.get("claude_code") is before_class

    def test_collects_created_sessions(self):
        with with_fake_session_registry() as fake_cls:
            assert fake_cls.created() == []
            registry = get_default_registry()
            sess = registry.create("fake", _config(worker_id="alice"))
            assert isinstance(sess, FakeSession)
            assert len(fake_cls.created()) == 1
            assert fake_cls.created()[0].config.worker_id == "alice"

    def test_log_is_reset_between_contexts(self):
        with with_fake_session_registry() as fake_cls:
            registry = get_default_registry()
            registry.create("fake", _config(worker_id="x"))
            assert len(fake_cls.created()) == 1

        # New context — log should be fresh
        with with_fake_session_registry() as fake_cls:
            assert fake_cls.created() == []

    def test_intercept_providers_can_be_narrowed(self):
        with with_fake_session_registry(intercept_providers=("fake",)):
            registry = get_default_registry()
            assert registry.has("fake")
            assert not registry.has("claude_code")

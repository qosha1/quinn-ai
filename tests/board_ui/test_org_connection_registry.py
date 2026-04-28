"""Direct unit tests for OrgConnectionRegistry + connect_with_retry."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from board_ui.services.org_connection import (
    DatabaseLocked,
    DatabaseNotFound,
    OrgConnectionError,
    OrgNotFound,
)
from board_ui.services.org_connection_registry import (
    OrgConnectionRegistry,
    connect_with_retry,
)


@pytest.fixture
def fake_conn():
    return MagicMock(name="QuinnAIOrgConnection")


class TestRegistryBasics:
    def test_empty_registry_has_no_active(self):
        reg = OrgConnectionRegistry()
        assert reg.active is None
        assert reg.active_path is None
        assert len(reg) == 0
        assert Path("/anywhere") not in reg

    def test_add_does_not_change_active(self, fake_conn):
        reg = OrgConnectionRegistry()
        reg.add(Path("/a"), fake_conn)
        assert len(reg) == 1
        assert Path("/a") in reg
        assert reg.active_path is None  # add does not implicitly activate

    def test_activate_sets_active_path(self, fake_conn):
        reg = OrgConnectionRegistry()
        reg.add(Path("/a"), fake_conn)
        assert reg.activate(Path("/a")) is True
        assert reg.active_path == Path("/a")
        assert reg.active is fake_conn

    def test_activate_unregistered_path_returns_false(self):
        reg = OrgConnectionRegistry()
        assert reg.activate(Path("/missing")) is False
        assert reg.active_path is None

    def test_get_returns_connection_or_none(self, fake_conn):
        reg = OrgConnectionRegistry()
        reg.add(Path("/a"), fake_conn)
        assert reg.get(Path("/a")) is fake_conn
        assert reg.get(Path("/missing")) is None


class TestRegistryDisconnect:
    def test_disconnect_active_with_no_others_clears_active(self, fake_conn):
        reg = OrgConnectionRegistry()
        reg.add(Path("/a"), fake_conn)
        reg.activate(Path("/a"))
        new_active = reg.disconnect()
        assert new_active is None
        assert reg.active_path is None
        assert len(reg) == 0
        fake_conn.close.assert_called_once()

    def test_disconnect_active_with_others_switches_to_remaining(self):
        reg = OrgConnectionRegistry()
        c1, c2 = MagicMock(), MagicMock()
        reg.add(Path("/a"), c1)
        reg.add(Path("/b"), c2)
        reg.activate(Path("/a"))
        new_active = reg.disconnect()  # disconnects /a
        assert new_active == Path("/b")
        assert reg.active is c2
        c1.close.assert_called_once()
        c2.close.assert_not_called()

    def test_disconnect_specific_non_active_keeps_active(self):
        reg = OrgConnectionRegistry()
        c1, c2 = MagicMock(), MagicMock()
        reg.add(Path("/a"), c1)
        reg.add(Path("/b"), c2)
        reg.activate(Path("/a"))
        new_active = reg.disconnect(Path("/b"))
        assert new_active == Path("/a")  # unchanged
        c2.close.assert_called_once()
        c1.close.assert_not_called()

    def test_disconnect_swallows_close_errors(self, fake_conn):
        reg = OrgConnectionRegistry()
        fake_conn.close.side_effect = RuntimeError("boom")
        reg.add(Path("/a"), fake_conn)
        reg.activate(Path("/a"))
        # Should not raise
        reg.disconnect()
        assert reg.active_path is None


class TestConnectWithRetry:
    @pytest.mark.asyncio
    async def test_returns_connection_immediately_on_success(self, fake_conn):
        factory = MagicMock(return_value=fake_conn)
        result = await connect_with_retry(
            Path("/a"), max_retries=3, connection_factory=factory
        )
        assert result is fake_conn
        assert factory.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_database_locked_then_succeeds(self, fake_conn):
        sleeps = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        attempts = [
            DatabaseLocked(Path("/a/db"), Exception("locked")),
            DatabaseLocked(Path("/a/db"), Exception("locked")),
            fake_conn,
        ]

        def factory(_path):
            v = attempts.pop(0)
            if isinstance(v, Exception):
                raise v
            return v

        result = await connect_with_retry(
            Path("/a"),
            max_retries=3,
            connection_factory=factory,
            sleep=fake_sleep,
        )
        assert result is fake_conn
        assert sleeps == [0.5, 1.0]  # exponential backoff

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        async def fake_sleep(_delay):
            pass

        def always_locked(_path):
            raise DatabaseLocked(Path("/a/db"), Exception("locked"))

        with pytest.raises(DatabaseLocked):
            await connect_with_retry(
                Path("/a"),
                max_retries=3,
                connection_factory=always_locked,
                sleep=fake_sleep,
            )

    @pytest.mark.asyncio
    async def test_propagates_org_not_found_immediately(self):
        def factory(_p):
            raise OrgNotFound(Path("/missing"))

        with pytest.raises(OrgNotFound):
            await connect_with_retry(
                Path("/missing"),
                max_retries=3,
                connection_factory=factory,
            )

    @pytest.mark.asyncio
    async def test_propagates_database_not_found_immediately(self):
        def factory(_p):
            raise DatabaseNotFound(Path("/a/db"))

        with pytest.raises(DatabaseNotFound):
            await connect_with_retry(
                Path("/a"), max_retries=3, connection_factory=factory
            )

    @pytest.mark.asyncio
    async def test_propagates_org_connection_error_immediately(self):
        def factory(_p):
            raise OrgConnectionError("nope")

        with pytest.raises(OrgConnectionError):
            await connect_with_retry(
                Path("/a"), max_retries=3, connection_factory=factory
            )

    @pytest.mark.asyncio
    async def test_on_locked_retry_callback_invoked(self, fake_conn):
        async def fake_sleep(_delay):
            pass

        events = []
        attempts = [
            DatabaseLocked(Path("/a/db"), Exception("locked")),
            fake_conn,
        ]

        def factory(_path):
            v = attempts.pop(0)
            if isinstance(v, Exception):
                raise v
            return v

        await connect_with_retry(
            Path("/a"),
            max_retries=3,
            connection_factory=factory,
            sleep=fake_sleep,
            on_locked_retry=lambda attempt, total, delay: events.append(
                (attempt, total, delay)
            ),
        )
        assert events == [(1, 3, 0.5)]

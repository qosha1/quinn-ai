"""Multi-org connection registry + retry-with-backoff connector.

Owns the (path → QuinnAIOrgConnection) dict and the "currently active" path.
Pure data — no UI dependencies — so callers (BoardApp) can stay thin and
the registry can be unit-tested with fake connections.
"""

import asyncio
from pathlib import Path
from typing import Callable, Optional

from .org_connection import (
    DatabaseLocked,
    DatabaseNotFound,
    OrgConnectionError,
    OrgNotFound,
    QuinnAIOrgConnection,
)


class OrgConnectionRegistry:
    """Hold open connections keyed by org path; track which is active."""

    def __init__(self) -> None:
        self._connections: dict[Path, QuinnAIOrgConnection] = {}
        self._active_path: Optional[Path] = None

    def __contains__(self, path: Path) -> bool:
        return path in self._connections

    def __len__(self) -> int:
        return len(self._connections)

    def add(self, path: Path, connection: QuinnAIOrgConnection) -> None:
        """Register a new connection. Does not change active path."""
        self._connections[path] = connection

    def get(self, path: Path) -> Optional[QuinnAIOrgConnection]:
        return self._connections.get(path)

    def items(self) -> dict[Path, QuinnAIOrgConnection]:
        return dict(self._connections)

    @property
    def active_path(self) -> Optional[Path]:
        return self._active_path

    @property
    def active(self) -> Optional[QuinnAIOrgConnection]:
        if self._active_path is None:
            return None
        return self._connections.get(self._active_path)

    def activate(self, path: Path) -> bool:
        """Mark `path` as active. Returns True if path is registered."""
        if path not in self._connections:
            return False
        self._active_path = path
        return True

    def disconnect(self, path: Optional[Path] = None) -> Optional[Path]:
        """Close + remove the connection at `path` (or active if None).

        Returns the new active path: another registered path, or None if no
        connections remain.
        """
        target = path or self._active_path
        if target is None:
            return self._active_path

        conn = self._connections.pop(target, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

        if target == self._active_path:
            self._active_path = (
                next(iter(self._connections), None) if self._connections else None
            )

        return self._active_path


async def connect_with_retry(
    org_path: Path,
    max_retries: int = 3,
    on_locked_retry: Optional[Callable[[int, int, float], None]] = None,
    sleep: Optional[Callable] = None,
    connection_factory: Optional[Callable[[Path], QuinnAIOrgConnection]] = None,
) -> QuinnAIOrgConnection:
    """Open a QuinnAIOrgConnection with backoff on DatabaseLocked.

    Args:
        org_path: Path to the org directory.
        max_retries: Total attempts (including the first). Default 3 → up to
            two retries with 0.5s, 1.0s backoff.
        on_locked_retry: Called as (attempt, max_retries, delay_seconds) before
            each retry sleep — useful for surfacing progress to the user.
        sleep: Async sleep injection point (tests pass a synchronous fake).
        connection_factory: Override for tests. When None, looks up
            QuinnAIOrgConnection at call time so tests can monkey-patch
            `board_ui.services.org_connection_registry.QuinnAIOrgConnection`.

    Raises:
        DatabaseLocked: After max_retries unsuccessful attempts.
        OrgNotFound, DatabaseNotFound, OrgConnectionError: Propagate immediately.
    """
    factory = connection_factory or QuinnAIOrgConnection
    # Resolve at call time so tests can patch asyncio.sleep globally.
    sleep_fn = sleep or asyncio.sleep
    last_locked: Optional[DatabaseLocked] = None
    for attempt in range(max_retries):
        try:
            return factory(org_path)
        except DatabaseLocked as e:
            last_locked = e
            if attempt >= max_retries - 1:
                break
            delay = 0.5 * (2**attempt)
            if on_locked_retry:
                on_locked_retry(attempt + 1, max_retries, delay)
            await sleep_fn(delay)
        except (OrgNotFound, DatabaseNotFound, OrgConnectionError):
            raise

    assert last_locked is not None  # loop only exits via raise or last_locked set
    raise last_locked

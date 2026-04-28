"""ScenarioHarness — context manager that wires tmp dir + FakeSpawner."""
from __future__ import annotations

import shutil
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from .db import DBHandle
from .ops import OPS
from .predicates import PREDICATES
from .spec import ScenarioSpec


class ScenarioRun:
    """Live state during a scenario execution."""

    def __init__(self, harness: "ScenarioHarness", org_path: Path, spawner: Any) -> None:
        self.harness = harness
        self.org_path = org_path
        self.spec = harness.spec
        self.runner = CliRunner()
        self.spawner = spawner
        self.context: dict[str, Any] = {}
        self._db: DBHandle | None = None

    @property
    def db(self) -> DBHandle:
        if self._db is None:
            self._db = DBHandle(self.org_path)
        return self._db

    def _close_db(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def run_op(self, op: dict[str, Any]) -> None:
        kind = op.get("op")
        if kind not in OPS:
            raise KeyError(f"unknown op: {kind!r} (known: {sorted(OPS.keys())})")
        # Refresh DB connection per op so writes are visible.
        self._close_db()
        OPS[kind](self, op)

    def check(self, assertion: dict[str, Any]) -> str | None:
        kind = assertion.get("kind")
        if kind not in PREDICATES:
            raise KeyError(
                f"unknown assertion: {kind!r} (known: {sorted(PREDICATES.keys())})"
            )
        # Refresh DB connection so we see the latest writes.
        self._close_db()
        return PREDICATES[kind](self, assertion)

    def _resolve_worker_id(self, name_or_id: str) -> str:
        """Map a scenario-level name (or 'ceo' alias) to the worker's DB id."""
        # If it looks like an id (contains a dash or matches no name), pass through.
        worker = self.db.find_worker_by_name(name_or_id)
        if worker is not None:
            return worker["id"]
        return name_or_id  # fall through; let CLI surface the error


class ScenarioHarness:
    """Context manager that prepares an isolated org dir + FakeSpawner registry."""

    def __init__(self, spec: ScenarioSpec) -> None:
        self.spec = spec
        self._stack: ExitStack | None = None
        self._tmpdir: str | None = None

    def __enter__(self) -> ScenarioRun:
        if self._stack is not None:
            raise RuntimeError("ScenarioHarness cannot be re-entered")

        # Create exit stack so we can register cleanup that runs in reverse order
        self._stack = ExitStack()
        try:
            # Tmp dir for the org
            self._tmpdir = tempfile.mkdtemp(prefix=f"scenario-{self.spec.name}-")
            org_path = Path(self._tmpdir) / "org"
            org_path.mkdir()

            # Swap spawner registry — this returns a context manager
            from cli.tests.harness.fake_spawner import with_fake_spawner

            spawner = self._stack.enter_context(with_fake_spawner())

            # Register cleanup of tmp dir
            self._stack.callback(self._cleanup_tmpdir)

            run = ScenarioRun(self, org_path, spawner)
            self._run = run

            # If setup specifies an init block, run init now (most scenarios start
            # by initializing the org; running it implicitly here saves boilerplate
            # in every YAML file).
            if "init" in self.spec.setup:
                run.run_op({"op": "init"})

            return run
        except Exception:
            self._stack.close()
            self._stack = None
            self._cleanup_tmpdir()
            raise

    def __exit__(self, *exc) -> None:
        try:
            if hasattr(self, "_run"):
                self._run._close_db()
        finally:
            if self._stack is not None:
                self._stack.close()
                self._stack = None

    def _cleanup_tmpdir(self) -> None:
        if self._tmpdir and Path(self._tmpdir).exists():
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        self._tmpdir = None

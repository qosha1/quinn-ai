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
    """Context manager that prepares an isolated org dir + (optionally) FakeSpawner.

    By default swaps the spawner registry to FakeSpawner for deterministic
    Tier-2 scenarios. Pass use_fake_spawner=False (e.g. from the live canary
    in Tier 3) to keep the real registry so spawned sessions hit a real
    provider like claude_code.
    """

    def __init__(self, spec: ScenarioSpec, *, use_fake_spawner: bool = True) -> None:
        self.spec = spec
        self.use_fake_spawner = use_fake_spawner
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

            spawner = None
            if self.use_fake_spawner:
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
            # Capture per-worker tmux pane snapshots BEFORE db closes so we
            # have forensic evidence of what each worker was doing at the
            # moment the scenario ended (qim4: needed to diagnose canary 09's
            # CEO-doesn't-act stall). Best-effort — never fails the scenario.
            if hasattr(self, "_run") and self._tmpdir:
                self._capture_post_mortem()
            if hasattr(self, "_run"):
                self._run._close_db()
        finally:
            if self._stack is not None:
                self._stack.close()
                self._stack = None

    def _cleanup_tmpdir(self) -> None:
        # When QUINNAI_SCENARIO_KEEP_TMPDIR=1 (qim4 diagnostic mode), preserve
        # the org tmpdir so the operator can inspect post-mortem files +
        # beads/db state after the run.
        import os
        if os.environ.get("QUINNAI_SCENARIO_KEEP_TMPDIR") == "1":
            if self._tmpdir:
                print(f"[harness] preserving tmpdir for post-mortem: {self._tmpdir}")
            self._tmpdir = None
            return
        if self._tmpdir and Path(self._tmpdir).exists():
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        self._tmpdir = None

    def _capture_post_mortem(self) -> None:
        """Write each live worker's tmux pane scrollback to post_mortem/.

        Called from __exit__ before cleanup so we capture state at the
        moment the scenario ended (regardless of pass/fail). The captures
        live inside the tmpdir so they're preserved when
        QUINNAI_SCENARIO_KEEP_TMPDIR=1.
        """
        import subprocess
        try:
            run = self._run
            db = run.db
            # Workers table — get all known workers and their tmux session names.
            rows = db.conn.execute(
                "SELECT id, name, role FROM workers"
            ).fetchall()
        except Exception as e:
            print(f"[harness] post-mortem db read failed: {e}")
            return

        post_mortem_dir = Path(self._tmpdir) / "post_mortem"
        try:
            post_mortem_dir.mkdir(exist_ok=True)
        except Exception:
            return

        for row in rows:
            worker_id = row["id"]
            name = row["name"]
            session = f"qn-{worker_id}"
            try:
                # Capture full scrollback (-S -). check=False so missing
                # session = empty file with stderr captured.
                result = subprocess.run(
                    ["tmux", "capture-pane", "-t", session, "-p", "-S", "-"],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                content = result.stdout if result.returncode == 0 else (
                    f"[capture-pane failed rc={result.returncode}: "
                    f"{result.stderr.strip()!r}]\n"
                )
                safe_name = name.replace("/", "_").replace(" ", "_")
                (post_mortem_dir / f"{worker_id}_{safe_name}.txt").write_text(content)
            except Exception as e:
                # Best-effort — don't break exit on any worker
                try:
                    (post_mortem_dir / f"{worker_id}_ERROR.txt").write_text(
                        f"capture exception: {e}\n"
                    )
                except Exception:
                    pass

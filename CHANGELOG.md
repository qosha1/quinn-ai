# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.3.0] - 2026-04-29

### Added
- E2E test suite (`tests/e2e/`, ~70 tests, ~3 min wall) hitting real `qn` + real `bd` against `tmp_path` orgs — no mocks at the integration boundary. Covers org init/start/status/stop, OKR set/list/cascade/close, hire/fire/promote/demote, wrkr session ops, board pause/resume/fire, provider config. New `make test-e2e` target + dedicated CI job.
- Tier 2 scenario test framework (`tests/scenarios/`): YAML-driven scenarios auto-discovered by `pytest_generate_tests`, executed via in-process Click `CliRunner` + `FakeSpawner`. 13 op handlers, 10 assertion predicates.
- Tier 3 live LLM canary (`tests/canary/`): paid end-to-end validation against real Anthropic. Multi-worker scenarios (CEO hires Bob+Carol → exchange DMs via msgr; CEO delegates authority to Diana → Diana hires + funds Eve+Frank).
- `qn org init --reuse-beads` flag: explicit opt-in for sharing an existing `.beads/` tracker. Default is now to refuse, preventing accidental cross-project bead pollution.
- `qn org init --skip-okrs`: actually suppresses the bootstrap OKR (was previously only suppressing the prompt).
- `qn org start --model <id>` (envvar `QUINNAI_CANARY_MODEL`): pin the LLM model the spawned CEO session uses. Threads through `SessionConfig.model` to claude CLI's `--model` flag.
- `qn org okr close <id>`: writes to BOTH the bead and the SQLite mirror so `qn org okr list --from-db` reflects closure.
- `find_worker_id_from_cwd()` discovery helper: third resolution rung after `--worker-id` flag and `$QUINN_WORKER_ID` env. msgr + qn-bd also fall back to the tmux session name (`qn-wrkr-XXX`) for full bullet-proofing against env scrubbing.
- Board UI: real modal screens for the team view (`HireWorkerModal`, `WorkerActionsModal`, `ConfirmFireModal`) replacing the "use the CLI" notification stubs. `org_hire`/`org_promote`/`org_demote` added to `qn_cli_client`. Org tabs split into separate select + close (×) buttons.
- Worker onboarding: `BRIEFING.md` now includes a "How to Break Down Work" section coaching the CEO/manager to decompose along (vertical × skillset) rather than executing solo.
- `cli/tests/test_bd_flag_drift.py`: parametrized test that probes `bd <subcmd> --help` for every flag we pass — catches future bd flag drift after a binary upgrade.
- `examples/org-scripts/common/check-env.sh --setup-only` flag for init-only flows that don't need provider credentials.

### Changed
- `qn org okr list` no longer has two contradictory views. Single merged output: status from the SQLite mirror, priority/labels from beads, KRs/progress from sqlite. `--from-db` kept as a deprecated no-op alias.
- `qn org init` refuses to share an existing `.beads/` at the target path unless `--reuse-beads` is passed.
- `Org.start()` Python API now wraps CEO onboarding in try/except and reverts CEO lifecycle on failure (no more half-activated state). The CLI orchestrator additionally rolls back org status on transition failure.
- `Worker.spawn_session` reordered phases: budget enforcement runs BEFORE worker_state row creation. Hires that hit `NoBudgetAllocationError` no longer leave a stale `runtime_status='starting'` row behind.
- `find_orphaned_tmux_sessions` scoped to THIS org's workers — extracts `wrkr-id` from each `qn-{wrkr-id}` session name and only considers it an orphan if the id is in our workers table. Multi-org machines no longer have org A killing org B's sessions on startup.
- `qn org delegate-authority --level <preset> --budget X` flips `can_delegate=True` on the delegate's allocation so they can sub-allocate to their own reports.
- `qn org stop` summary now surfaces unacked workers as a clear ⚠ warning block on stderr (was a buried log line).
- TmuxSpawner subprocess invocations now pass `stdin=subprocess.DEVNULL` so the tmux server doesn't inherit pytest's captured fd. No more `pytest -s` workaround for canary runs.
- `claude_code` adapter strips `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` from the spawn env (both via the env dict AND by wrapping the command with `env -u <KEYS>`) so claude-CLI uses its own OAuth without an "Auth conflict" warning.
- `--org-path` help text unified across `qn`, `qn org`, `qn wrkr`, `qn board` — all now describe the actual precedence (`--org-path` > `$QUINN_ORG_PATH` > cwd auto-detect).
- Default Anthropic model IDs refreshed to current 4.X family: `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` (in `cli/providers/anthropic.py` and the `providers.yaml` template).
- 4 stale Jan-2026 audit/design docs marked with prominent ⚠ HISTORICAL banners pointing at the implementing code.
- `STATEMACHINES.md` refreshed: 12 stale `Broken`/`Partial` status labels updated to `Implemented` (the gaps had been closed since Jan 2026 but the spec wasn't updated). Jan 2026 validation report tagged historical.

### Removed
- `working` and `blocked` from `RUNTIME_STATES`/`RUNTIME_TRANSITIONS` — vestigial states with no production code writing them and no transition machinery. Task-level state lives at the bead/issue layer.
- 4 dead module-shadow facade files: `cli/core/queries.py`, `cli/core/db.py`, `cli/core/worker.py`, `cli/core/notifications.py` (all shadowed by their respective packages, never executed; 302 lines of dead code).
- 21 stale `@pytest.mark.skipif(LogReader is None)` TDD-placeholder decorators in `test_log_reader.py` (LogReader has been implemented for months).
- 13 stale `@pytest.mark.xfail` decorators on state-machine tests (the underlying violations were fixed since Jan 2026 but xfail decorators were never removed).

### Fixed
- `qn org init` could silently share a parent project's `.beads/` and pollute its tracker.
- `qn org hire` left workers stuck in `runtime_status='starting'` when budget allocation didn't exist yet.
- `qn org hire`-spawned workers couldn't use msgr / qn-bd because env didn't propagate through claude's Bash tool. Triple fallback now: explicit flag → env var → cwd → tmux session name.
- SQLite default datetime adapter deprecation warnings (Python 3.12+) — every test run was emitting hundreds. Registered explicit ISO-8601 adapter+converter at module init.
- `archive.sh` `duration_seconds=-1` because qn writes ISO 8601 (`T` separator + microseconds) but archive's `date -f` wanted `%Y-%m-%d %H:%M:%S`. Added `_normalize_ts()` helper.
- FTS5 wrkr search crashed on hyphenated queries (`'no-such-string'` parsed as boolean operators). Sanitize via phrase-quoting.
- `qn config set-provider` rejected `codex`/`gemini` despite `qn org provider list` shipping them. Choices now derive from the registry.
- 4 board_ui async tests missing `@pytest.mark.asyncio` decorator + 1 stale post-merge `tests.test_e2e_org_discovery` patch target.
- `qn org init` template no longer shows the redundant `Role: CEO` line in `WELCOME.md`/`BRIEFING.md` when the worker name equals the role (placeholder-CEO case).
- `cli/core/org_init/scaffolding.py:init_beads()` switched from `--non-interactive` (removed in bundled bd 0.43+) to `--quiet` (works on both bundled and system bd).
- 5 pre-existing `tests/board_ui/` import collection errors (`from tests.conftest` should have been `from .conftest` post-board-merge).
- `qn org init` shim in `example_orgs/org-scripts/common/qn` used bare `python3` which broke ~50 tests on systems without quinnai's deps in the global python. Now prefers `<repo>/.venv/bin/python` or `$QUINNAI_PYTHON`.
- 4 magic-number `time.sleep(N)` calls in `org_start_controller.py` extracted to named constants in `cli/core/constants/timing.py`.
- ADR file naming standardized (`003-*.md`/`004-*.md` → `ADR-003-*.md`/`ADR-004-*.md`); added directory README documenting the ADR-006 gap.

---

## [0.2.1] - 2026-04-27

### Added
- `[board]` extra: install with `pip install quinnai[board]` to pull in the Textual TUI dependency. The `qn board` command group ships in the base package; the dependency is opt-in.
- `tests/board_ui/` test suite (was `terminal-app/tests/`); `make test-board` target.

### Changed
- Merged the standalone `terminal-app/` package into the main `quinnai` distribution. The board UI now lives under `cli.commands.board` and `board_ui/` (top-level package). The separate `terminal-app/` directory was removed.
- `cli/core/session.py` split into a `cli/core/session/` package (types/exceptions/interface) for clearer surface area.
- `cli/core/org_init.py` split into `cli/core/org_init/` package (types/scaffolding/bootstrap/init).
- `cli/commands/org/okr.py` split into `cli/commands/org/okr/` package.
- `shared/escalation/manager.py` (864L) split into types/config/manager.
- `WorkerBridge` moved from `shared.pyterm` to `cli.core.pyterm`.
- pyterm `SessionState` / `SessionConfig` / `ProviderConfig` renamed with `Pyterm` prefix to disambiguate from session-provider config.

### Removed
- `cli/core/worker.py.bak` (71KB tracked backup).
- `TranscriptRepository` (wrong layer, zero prod consumers).

### Fixed
- Reconciled triplicated `SessionConfig` / `ProviderConfig` / `PromptResult` definitions into a single source of truth.
- Encapsulated `cli.core.logging` module state behind `_LoggingState` to avoid module-level global mutation.
- Hoisted `WorkerBridge` imports + rerouted test patches; inlined `TMUX_ATTACH_WAIT`.
- PyPI publish step now uses `--skip-existing` to avoid double-upload errors.

---

## [0.2.0] - 2026-04-25

### Removed
- B2B SaaS template residue: Django backend, NextJS dashboard and landing site, Playwright e2e suite, Docker Compose infrastructure, multi-tenant auth/billing/teams test scaffolding.
- `Makefile` template-fetch / template-diff / template-merge / template-cherry targets and the upstream b2b-saas-template remote workflow.
- `openspec/changes/` proposals tied to the B2B stack (auth-teams, backend-django-core, billing-stripe, comprehensive-testing, docker-infrastructure, frontend-app, landing-page).
- `.envs/` Django/Postgres environment templates and the `verify-setup.sh` script that validated them.
- `release-notes/TEMPLATE.md`, `DEPLOYMENT.md`, `DOCKER.md`.

### Added
- `tests/test_no_b2b_residue.py` and `tests/test_no_b2b_imports.py` guardrails to keep B2B template artifacts from creeping back in.

### Fixed
- `VERSION` and `pyproject.toml` versions now both report `0.2.0` (previously diverged at 0.2.0 / 0.1.0).
- Removed stale `.envs/.local/.django` references from `cli/commands/config.py`, `scripts/setup-dev.sh`, `scripts/run-board.sh`, `scripts/run-qn.sh`.
- Replaced upstream `YOUR_ORG/b2b-saas-template` GitHub URLs in `scripts/bump-version.sh` with this repository.

---

[Unreleased]: https://github.com/qosha1/quinn-ai/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/qosha1/quinn-ai/releases/tag/v0.2.0

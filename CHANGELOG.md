# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

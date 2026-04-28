# E2E Tests

End-to-end tests for QuinnAI CLI commands. These exercise the real `qn` binary
and a real `bd` binary against a `tmp_path` org — no mocks at the integration
boundary.

## Purpose

Verify that actual CLI commands work end-to-end, catching issues that unit tests miss:

- Org path auto-detection
- Database migrations
- Config file validation
- Directory structure creation
- State transitions
- Command-line argument parsing
- Error message quality
- bd integration (OKRs, beads-backed lifecycle work)
- Worker hire/fire/promote flows
- Board intervention (pause/resume/fire)

## Test Structure

### Test Files

Smoke tests (org lifecycle):

- `test_smoke_org_init.py` — `qn org init`
- `test_smoke_org_status.py` — `qn org status`
- `test_smoke_org_start.py` — `qn org start`
- `test_smoke_org_stop.py` — `qn org stop`
- `test_smoke_full_workflow.py` — full init→start→status→stop

End-to-end command coverage:

- `test_e2e_okr_workflow.py` — `qn org okr` set/add/list/show/progress/cascade/update-kr/link
- `test_e2e_hire_fire.py` — `qn org hire/fire/promote/demote/delegations`
- `test_e2e_wrkr_commands.py` — `qn wrkr status/get-work/search/report`
- `test_e2e_intervention.py` — `qn board status/alerts/health/pause/resume/fire`
- `test_e2e_provider.py` — `qn config set-provider/validate` and `qn org provider list`
- `test_e2e_full_lifecycle.py` — composed init→start→OKR→hire→intervene→stop

### Fixtures (conftest.py)

- `temp_org_dir` — temporary directory for org testing
- `cli_runner` — runs CLI commands via subprocess (used by smoke tests)
- `qn_runner` — same idea, looks up `qn` from PATH (used by `test_e2e_*`)
- `initialized_org` — pre-initialized org
- `running_org` / `org_with_ceo` — pre-started org with CEO
- `hired_team` — parametrizable factory that hires N workers under the CEO
- `mock_provider_config` — minimal provider configuration
- `env_hygiene` (autouse) — strips ambient `QUINN_*` and provider API key env vars
  so the dev shell can't bleed credentials into the test process
- Module-level `pytest.skip` gate — skips the entire suite cleanly when no `bd`
  binary is available on PATH or in `cli/bin/{platform}/bd`

## Running Tests

```bash
# Canonical: from project root
make test-e2e

# Or directly with pytest
.venv/bin/pytest tests/e2e/ -v --timeout=180

# Single file
.venv/bin/pytest tests/e2e/test_e2e_okr_workflow.py -v

# Single test
.venv/bin/pytest tests/e2e/test_e2e_hire_fire.py::test_hire_under_ceo_succeeds -v
```

## Test Philosophy

1. **Use subprocess, not imports** — run actual CLI commands against the installed `qn` binary
2. **No mocks at the integration boundary** — real `bd`, real SQLite, real filesystem
3. **One org per test** — each test gets an isolated `tmp_path` org
4. **Verify exit codes AND stdout/stderr** — a non-zero exit isn't enough on its own
5. **Avoid spawning real LLM sessions** — pass `--no-spawn-ceo` / `--skip-config-validation`
6. **Use `--force` / `--yes`** to skip interactive confirmations
7. **Read from SQLite directly** when verifying side effects, but always set up via `qn`

## What These Tests Catch

Real bugs surfaced or pinned by this suite:

1. Auto-detection failures across nested working directories
2. Database migration failures on startup
3. Provider config validation gaps
4. Missing required directories after init
5. Invalid state transitions not caught by unit tests
6. CLI argument plumbing bugs (placement of `--worker-id`, `--org-path`)
7. Cryptic error messages that should be actionable
8. bd integration regressions (OKR cascade, link, update-kr)
9. Worker lifecycle edge cases (firing the CEO, firing unknown ID)
10. Board intervention safety (interactive confirm gates, force flag)

## CI/CD Integration

E2E runs as its own job in `.github/workflows/test-integration.yml`:

```yaml
e2e-tests:
  steps:
    - Install qn (cli + terminal-app)
    - Install bd (cargo install --locked --git ...)
    - .venv/bin/pytest tests/e2e/ --timeout=180 -v
```

The bd install step is `continue-on-error: true` because the conftest skip gate
will skip the whole suite cleanly if `bd` isn't installed — the job won't fail
spuriously, but it also won't silently pass without coverage.

## Adding New Tests

When adding a new CLI command:

1. Create `test_e2e_{command}.py` (or extend an existing file)
2. Use `qn_runner` + a fixture (`initialized_org`, `running_org`, `hired_team`) for setup
3. Cover: success, errors, edge cases, auto-detection (where relevant)
4. Update `COVERAGE.md` with the new test count
5. Run the full suite to verify no regressions

## Performance

| Suite | Tests | Runtime |
|-------|-------|---------|
| Smoke (`test_smoke_*`) | 31 | ~50s |
| E2E (`test_e2e_*`) | 37 | ~140s |
| **Full suite** | **68** | **~3 min** |

To keep tests fast:

- Use `--no-spawn-ceo` to skip session spawning
- Use `--skip-config-validation` for start when validation isn't the SUT
- Use `--force` / `--yes` to bypass confirmations
- Reuse fixtures (`initialized_org`, `running_org`) instead of re-initing per test

## Debugging

```bash
# Verbose output
.venv/bin/pytest tests/e2e/ -v --log-cli-level=DEBUG

# Single test with stdout visible
.venv/bin/pytest tests/e2e/test_e2e_hire_fire.py::test_hire_under_ceo_succeeds -s -v

# Keep temp dirs for inspection
.venv/bin/pytest tests/e2e/ --basetemp=/tmp/pytest-debug
```

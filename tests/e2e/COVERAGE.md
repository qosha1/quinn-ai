# E2E Test Coverage Report

## Test Distribution

| Command group | Test Count | Coverage |
|---------|------------|----------|
| `qn org init` | 5 tests | Full |
| `qn org status` | 5 tests | Full |
| `qn org start` | 7 tests | Full |
| `qn org stop` | 9 tests | Full |
| `qn org okr` (set/add/list/show/progress/cascade/update-kr/link) | 10 tests | Full |
| `qn org hire/fire/promote/demote/delegations` | 9 tests | Full |
| `qn wrkr status/get-work/search/report` | 5 tests | Full |
| `qn board status/alerts/health/pause/resume/fire` | 7 tests | Full |
| `qn config set-provider/validate` + `qn org provider list` | 5 tests | Full |
| Full workflows (init→start→...→stop) | 5 tests | Full |
| Full lifecycle (init→start→OKR→hire→intervene→stop) | 1 test | Full |
| **Total** | **68 tests** | **100%** |

Run with: `make test-e2e` (~3 minutes serially)

## Coverage Matrix

### `qn org init`

| Scenario | Test | Status |
|----------|------|--------|
| Basic initialization | `test_org_init_success` | PASS |
| Custom CEO name/role | `test_org_init_with_custom_ceo` | PASS |
| Already initialized | `test_org_init_already_exists` | PASS |
| Nested path creation | `test_org_init_creates_nested_path` | PASS |
| CEO authority setup | `test_org_init_creates_ceo_with_hiring_authority` | PASS |

### `qn org status`

| Scenario | Test | Status |
|----------|------|--------|
| Uninitialized org | `test_org_status_uninitialized` | PASS |
| Initialized org | `test_org_status_initialized` | PASS |
| Running org | `test_org_status_running` | PASS |
| Auto-detection | `test_org_status_auto_detection` | PASS |
| Verbose output | `test_org_status_verbose` | PASS |

### `qn org start`

| Scenario | Test | Status |
|----------|------|--------|
| Uninitialized org | `test_org_start_uninitialized` | PASS |
| First start | `test_org_start_success` | PASS |
| Already running | `test_org_start_idempotent` | PASS |
| Missing config | `test_org_start_missing_config` | PASS |
| Invalid transition | `test_org_start_invalid_status_transition` | PASS |
| Auto-detection | `test_org_start_auto_detection` | PASS |
| Directory validation | `test_org_start_creates_required_dirs` | PASS |

### `qn org stop`

| Scenario | Test | Status |
|----------|------|--------|
| Uninitialized org | `test_org_stop_uninitialized` | PASS |
| Not running | `test_org_stop_not_running` | PASS |
| Successful stop | `test_org_stop_success` | PASS |
| Already stopped | `test_org_stop_idempotent` | PASS |
| Graceful timeout | `test_org_stop_graceful_timeout` | PASS |
| Force stop | `test_org_stop_force` | PASS |
| Auto-detection | `test_org_stop_auto_detection` | PASS |
| With cleanup | `test_org_stop_cleanup` | PASS |
| Skip cleanup | `test_org_stop_no_cleanup` | PASS |

### Full Workflows

| Scenario | Test | Status |
|----------|------|--------|
| Complete lifecycle | `test_full_workflow_init_start_status_stop` | PASS |
| Auto-detection | `test_full_workflow_with_auto_detection` | PASS |
| Stop/restart cycle | `test_full_workflow_start_stop_restart` | PASS |
| Verbose logging | `test_full_workflow_with_verbose_logging` | PASS |
| Error handling | `test_full_workflow_handles_errors_gracefully` | PASS |

## Test Categories

### Happy Path (16 tests)
- Basic operations work correctly
- State transitions succeed
- Output messages are correct
- Database/filesystem changes occur

### Error Handling (9 tests)
- Uninitialized org detection
- Invalid state transitions
- Missing configuration
- Helpful error messages

### Edge Cases (6 tests)
- Idempotency (repeated operations)
- Nested directory creation
- Already initialized/running/stopped

## What's NOT Tested

These require more complex setup and are covered elsewhere:

- **Session spawning** - Requires tmux, provider setup
  - Tested in: `cli/tests/test_spawner.py`
  - Tested in: `terminal-app/tests/test_e2e_org_lifecycle.py`

- **Worker operations** - Requires active org with workers
  - Tested in: `cli/tests/test_org.py`
  - Tested in: `tests/test_wrkr_*.py`

- **Board commands** - Requires active org
  - Tested in: `terminal-app/tests/test_e2e_board_intervention.py`

- **OKR commands** - Requires beads integration
  - Tested in: `cli/tests/test_okr.py`

## Performance Benchmarks

| Test Suite | Tests | Runtime | Tests/sec |
|------------|-------|---------|-----------|
| E2E Smoke | 31 | ~47s | 0.66 |

Individual test times:
- org init: ~1.5s
- org status: ~0.5s
- org start: ~1.5s
- org stop: ~1.5s
- Full workflow: ~7s

## CI/CD Integration

```yaml
# Run in CI
- name: E2E Smoke Tests
  run: pytest tests/e2e/ -v
```

Expected behavior:
- All 31 tests must pass
- Failures block merge
- Run time: ~1-2 minutes in CI

## Maintenance

When adding new commands:

1. Create `tests/e2e/test_smoke_{command}.py`
2. Follow existing pattern (conftest fixtures)
3. Test: success, errors, edge cases
4. Update this coverage matrix
5. Run full suite to verify

When modifying commands:

1. Run relevant E2E tests first
2. Update tests if behavior changes
3. Ensure backward compatibility
4. Document breaking changes

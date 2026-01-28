# Systemeval Testing Guide

QuinnAI uses [systemeval](https://github.com/your-org/systemeval) for integration testing. This guide explains how to run tests, write new tests, and debug failures.

## Quick Start

**Run all integration tests:**
```bash
systemeval test -c integration-all
```

**Run specific category:**
```bash
systemeval test -c baseline-org
systemeval test -c baseline-worker
systemeval test -c baseline-okr
```

**Run with coverage:**
```bash
systemeval test -c baseline-all --coverage
```

**Stop on first failure:**
```bash
systemeval test -c baseline-org --failfast
```

## Test Categories

Systemeval organizes tests into categories defined in `systemeval.yaml`:

**Baseline Tests:**
- `baseline-org`: Org lifecycle (init, start, stop, status)
- `baseline-worker`: Worker management (hire, fire, onboarding)
- `baseline-okr`: OKR management (set, list, show, update)
- `baseline-all`: All baseline tests

**E2E Tests:**
- `e2e-hello-world`: Hello-world example org workflow
- `e2e-startup-team`: Startup-team example org workflow
- `e2e-okr-driven`: OKR-driven example org workflow
- `e2e-all`: All E2E tests

**Aggregate:**
- `integration-all`: All integration tests (baseline + E2E)

## Test Structure

Integration tests use systemeval test harness with shared fixtures:

```python
def test_org_init(temp_org_factory, qn_runner):
    """Test org initialization."""
    org = temp_org_factory("test_init")

    result = qn_runner("org", "init", org_path=org)

    assert result.returncode == 0
    assert (org / "live" / "quinn.db").exists()
```

**Key Fixtures:**
- `temp_org_factory`: Creates isolated temp orgs with auto-cleanup
- `qn_runner`: Runs qn commands via subprocess
- `cleanup_org_sessions`: Kills tmux sessions (automatic)
- `verify_no_leaked_sessions`: Ensures cleanup (automatic)

## Writing New Tests

### 1. Choose Test File

Place tests in `tests/` directory:
- `test_baseline_org.py`: Org lifecycle tests
- `test_baseline_worker.py`: Worker management tests
- `test_baseline_okr.py`: OKR tests
- `test_e2e_*.py`: End-to-end workflow tests

### 2. Use Test Harness Fixtures

```python
def test_something(temp_org_factory, qn_runner):
    # Create isolated temp org
    org = temp_org_factory("test_name")

    # Run qn commands
    result = qn_runner("org", "init", org_path=org)

    # Assertions
    assert result.returncode == 0
    assert "expected output" in result.stdout
```

### 3. Test Pattern

**Setup:**
```python
org = temp_org_factory("unique_test_name")
qn_runner("org", "init", org_path=org)
```

**Execute:**
```python
result = qn_runner(
    "org", "start",
    "--no-spawn-ceo",
    "--skip-config-validation",
    org_path=org
)
```

**Verify:**
```python
assert result.returncode == 0
assert "running" in result.stdout.lower()

# Verify database state
db_path = org / "live" / "quinn.db"
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()
cursor.execute("SELECT status FROM org_state WHERE id = 'default'")
status = cursor.fetchone()[0]
conn.close()

assert status == "running"
```

**Cleanup (automatic):**
- Temp org deleted
- Tmux sessions killed
- No manual cleanup needed

### 4. Add to systemeval.yaml

```yaml
categories:
  my-feature:
    description: "My feature integration tests"
    pattern: "test_my_feature.py"
```

### 5. Run Your Tests

```bash
# Direct pytest
python -m pytest tests/test_my_feature.py -v

# Via systemeval
systemeval test -c my-feature
```

## Debugging Test Failures

**View full output:**
```bash
systemeval test -c baseline-org -v
```

**Stop on first failure:**
```bash
systemeval test -c baseline-org --failfast
```

**Run specific test:**
```bash
python -m pytest tests/test_baseline_org.py::TestOrgInit::test_init_creates_database -v
```

**Check command output:**
```python
result = qn_runner("org", "start", org_path=org, check=False)
print(f"Exit code: {result.returncode}")
print(f"stdout: {result.stdout}")
print(f"stderr: {result.stderr}")
```

**Inspect temp org:**
```python
# Add this before test ends to keep temp org
import time
print(f"Temp org at: {org}")
time.sleep(300)  # 5 minutes to inspect
```

**Check for leaked sessions:**
```bash
tmux list-sessions | grep quinn
```

## Common Issues

**Issue: Command not found**
- Solution: Ensure `qn` is in PATH or use absolute path
- Check: `which qn` or `source .venv/bin/activate`

**Issue: Tests timeout**
- Solution: Increase timeout in pytest.ini or workflow
- Check: Are sessions hanging? Kill with `tmux kill-session -t quinn-*`

**Issue: Temp org cleanup fails**
- Solution: Check `cleanup_org_sessions` fixture
- Manual: `rm -rf /tmp/quinn_test_*`

**Issue: Database locked**
- Solution: Close db connections in test
- Use: `conn.close()` after queries

**Issue: Worker tests fail with hiring authority error**
- Known limitation: CEO doesn't have hiring_authority_scope by default
- Status: Tests marked as skipped, will pass when feature is implemented

## CI Integration

Tests run automatically on:
- Push to main branch
- Pull requests

**GitHub Actions jobs:**
- `baseline-tests`: Fast baseline test suite
- `all-integration-tests`: Full suite with coverage
- `test-summary`: Aggregates results

**View results:**
- GitHub Actions tab in repository
- Coverage reports on Codecov

**Local CI simulation:**
```bash
# Run what CI runs
systemeval test -c baseline-all --failfast
systemeval test -c integration-all --coverage
```

## Performance Tips

**Parallel execution:**
```bash
pytest tests/ -n auto  # Requires pytest-xdist
```

**Skip slow tests:**
```bash
pytest tests/ -m "not slow"
```

**Run only fast tests:**
```bash
systemeval test -c baseline-org  # ~2 min
systemeval test -c baseline-okr  # ~1 min
```

## Best Practices

1. **Unique test names**: Use descriptive `temp_org_factory("name")` names
2. **Cleanup verification**: Tests should pass repeatedly without cleanup
3. **Check=False**: Use `check=False` when testing error cases
4. **Database queries**: Always close connections
5. **Tmux sessions**: Never spawn sessions without cleanup
6. **Test isolation**: Don't share state between tests
7. **Real commands**: Use actual qn commands, not mocked internals

## Reference

**Test counts (as of 2026-01-28):**
- Baseline org: 19 tests (all passing)
- Baseline worker: 16 tests (3 passing, 13 skipped)
- Baseline OKR: 9 tests (all passing)
- Test harness: 13 tests (all passing)
- Total: 57 tests (44 passing, 13 skipped)

**Files:**
- `tests/conftest.py`: Shared fixtures
- `tests/test_systemeval_harness.py`: Fixture validation
- `tests/test_baseline_org.py`: Org tests
- `tests/test_baseline_worker.py`: Worker tests
- `tests/test_baseline_okr.py`: OKR tests
- `systemeval.yaml`: Category definitions
- `.github/workflows/test-integration.yml`: CI config

**Documentation:**
- ADR-008: Systemeval integration testing architecture
- This guide: How to use systemeval for QuinnAI

## Getting Help

- **systemeval help**: `systemeval --help`
- **pytest help**: `python -m pytest --help`
- **Test failures**: Check GitHub Actions logs
- **Questions**: Open issue in repository

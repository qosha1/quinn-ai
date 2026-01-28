# ADR 008: Systemeval Integration Testing Architecture

**Status:** Proposed
**Date:** 2026-01-28
**Context:** quinnai-1erp.2 - Design systemeval test architecture for QuinnAI
**Related Epic:** quinnai-1erp - Systemeval Integration for QuinnAI CLI Testing

---

## Context and Problem Statement

QuinnAI has comprehensive unit tests (47 test files in cli/tests/) but lacks integration tests for real org lifecycles. Systemeval is configured with baseline and E2E test categories but not implemented.

Gaps:
1. **No org lifecycle tests** - init → start → stop workflows untested
2. **No worker hire/fire tests** - hiring workflows not validated end-to-end
3. **No OKR workflow tests** - OKR creation/tracking untested in real org context
4. **No E2E tests** - example_orgs configurations not tested
5. **No cleanup verification** - tmux sessions may leak after test failures

To ensure QuinnAI works correctly in production scenarios, we need comprehensive integration tests using systemeval that exercise real org lifecycles with proper setup/teardown.

## Decision Drivers

- **Real Workflows**: Test actual qn commands, not mocked internals
- **Isolation**: Tests must not interfere with each other or user orgs
- **Cleanup**: No leaked tmux sessions, temp files, or database connections
- **Performance**: Tests should run in <5 minutes for quick feedback
- **CI-Ready**: Must work in GitHub Actions without special infrastructure
- **Reproducibility**: Same test always produces same result

## Considered Options

### Option 1: Expand Unit Tests with More Mocking
- Add more tests to existing test_cli.py
- Mock more components to test complex workflows

**Pros:**
- Fast execution
- No cleanup needed
- Easy to debug

**Cons:**
- Doesn't test real qn command execution
- Mocks hide integration bugs
- Not representative of production use

### Option 2: Manual Testing Scripts
- Write shell scripts that run qn commands
- Manual execution and verification

**Pros:**
- Tests real commands
- Simple to write
- No test framework overhead

**Cons:**
- Not automated
- No CI integration
- Hard to maintain
- No assertions

### Option 3: Systemeval Integration Tests ✅ **SELECTED**
- Implement test_baseline_*.py files using subprocess
- Use systemeval categories for organization
- Shared fixtures for temp org creation/cleanup
- Real qn command execution with assertion validation

**Pros:**
- Tests real qn commands
- Automated and CI-ready
- Systemeval provides categorization and reporting
- Catches integration bugs mocks would miss
- Proper cleanup with pytest fixtures

**Cons:**
- Slower than unit tests
- Requires careful cleanup to prevent leaks

---

## Decision

**We will implement Option 3: Systemeval Integration Tests**

### Test Organization

**Directory Structure:**
```
tests/
├── conftest.py                  # Shared fixtures
├── test_baseline_org.py         # Org lifecycle integration
├── test_baseline_worker.py      # Worker lifecycle integration
├── test_baseline_comms.py       # Messaging integration
├── test_baseline_work.py        # Beads integration
├── test_baseline_okr.py         # OKR integration
├── test_e2e_hello_world.py      # Full hello-world workflow
├── test_e2e_startup_team.py     # Full startup-team workflow
└── test_e2e_okr_driven.py       # Full OKR-driven workflow
```

**Systemeval Categories** (already defined in systemeval.yaml):
- `baseline-org`: Org lifecycle tests
- `baseline-worker`: Worker lifecycle tests
- `baseline-comms`: Communication tests
- `baseline-work`: Work management tests
- `baseline-okr`: OKR tests
- `e2e-hello-world`: Hello-world E2E
- `e2e-startup-team`: Startup-team E2E
- `e2e-okr-driven`: OKR-driven E2E

### Test Fixtures (tests/conftest.py)

**temp_org_factory**:
```python
@pytest.fixture
def temp_org_factory():
    """Factory for creating isolated temp orgs with automatic cleanup."""
    orgs = []

    def _create_org(name="test_org"):
        tmpdir = tempfile.mkdtemp(prefix=f"quinn_test_{name}_")
        org_path = Path(tmpdir)
        orgs.append(org_path)
        return org_path

    yield _create_org

    # Cleanup: kill sessions, remove dirs
    for org_path in orgs:
        cleanup_org_sessions(org_path)
        shutil.rmtree(org_path, ignore_errors=True)
```

**qn_runner**:
```python
@pytest.fixture
def qn_runner(temp_org_factory):
    """Wrapper for running qn commands via subprocess."""
    def _run(*args, org_path=None, env=None, check=True):
        cmd = ["qn"]
        if org_path:
            cmd.extend(["--org-path", str(org_path)])
        cmd.extend(args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env or os.environ.copy(),
            check=False
        )

        if check and result.returncode != 0:
            raise AssertionError(
                f"Command failed: {' '.join(cmd)}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

        return result

    return _run
```

**cleanup_org_sessions**:
```python
def cleanup_org_sessions(org_path: Path):
    """Kill all tmux sessions associated with org."""
    if not org_path.exists():
        return

    # Get worker IDs from database
    db_path = org_path / "live" / "quinn.db"
    if not db_path.exists():
        return

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT worker_id FROM workers")
    worker_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Kill tmux sessions for each worker
    for worker_id in worker_ids:
        session_name = f"quinn-{worker_id}"
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            check=False
        )
```

### Test Pattern

**Baseline Org Lifecycle** (test_baseline_org.py):
```python
def test_org_full_lifecycle(qn_runner, temp_org_factory):
    """Test complete org lifecycle: init → start → stop."""
    org = temp_org_factory("lifecycle")

    # Init
    result = qn_runner("org", "init", org_path=org)
    assert result.returncode == 0
    assert (org / "live" / "quinn.db").exists()
    assert (org / "config" / "providers.yaml").exists()

    # Start (skip config validation, don't spawn CEO)
    result = qn_runner(
        "org", "start",
        "--no-spawn-ceo",
        "--skip-config-validation",
        org_path=org
    )
    assert result.returncode == 0
    assert "running" in result.stdout.lower()

    # Status
    result = qn_runner("org", "status", org_path=org)
    assert result.returncode == 0
    assert "running" in result.stdout.lower()

    # Stop
    result = qn_runner("org", "stop", org_path=org)
    assert result.returncode == 0
    assert "stopped" in result.stdout.lower()

    # Verify cleanup
    # (No tmux sessions should remain - checked by fixture cleanup)
```

**E2E Workflow** (test_e2e_hello_world.py):
```python
def test_hello_world_full_workflow(qn_runner, temp_org_factory):
    """Test hello-world example org workflow end-to-end."""
    org = temp_org_factory("hello_world")

    # Copy hello-world config
    example_config = Path("example_orgs/hello-world")
    shutil.copytree(example_config, org, dirs_exist_ok=True)

    # Run init script
    result = subprocess.run(
        [str(example_config / "scripts" / "init.sh"), str(org)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0

    # Verify org initialized correctly
    assert (org / "live" / "quinn.db").exists()

    # Run hello-world workflow
    # (Would execute actual workflow steps here)
```

### Setup/Teardown Strategy

**Setup (per test)**:
1. Create temp directory via `temp_org_factory`
2. Run `qn org init` with test-specific config
3. Use `--skip-config-validation` to avoid provider setup
4. Use `--no-spawn-ceo` to avoid spawning sessions in simple tests

**Teardown (automatic via fixtures)**:
1. Kill all tmux sessions associated with org (cleanup_org_sessions)
2. Close all database connections
3. Remove temp directory
4. Verify no leaked processes (check tmux list-sessions)

**Cleanup Verification**:
```python
@pytest.fixture(autouse=True, scope="session")
def verify_no_leaked_sessions():
    """Ensure no quinn tmux sessions leak across test runs."""
    yield

    result = subprocess.run(
        ["tmux", "list-sessions"],
        capture_output=True,
        text=True,
        check=False
    )

    quinn_sessions = [
        line for line in result.stdout.splitlines()
        if "quinn-" in line
    ]

    if quinn_sessions:
        raise AssertionError(
            f"Leaked tmux sessions detected:\n" +
            "\n".join(quinn_sessions)
        )
```

### Isolation Strategy

**Temp Directories**:
- Each test gets unique temp directory
- No shared state between tests
- Full cleanup after test completion

**Database Isolation**:
- Each org has separate SQLite database
- No shared database connections
- Close connections in cleanup

**Session Isolation**:
- Unique tmux session names per worker
- Session names include worker_id
- Kill sessions in cleanup

**Environment Isolation**:
- Tests don't modify user's environment
- Use subprocess env parameter for test-specific env vars
- Don't set global environment variables

### CI Integration

**GitHub Actions** (.github/workflows/test-integration.yml):
```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  systemeval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt

      - name: Run baseline tests
        run: systemeval test -c baseline-all --failfast --coverage

      - name: Run E2E tests
        run: systemeval test -c e2e-all --failfast

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

**Local Development**:
```bash
# Run all integration tests
systemeval test -c baseline-all -c e2e-all

# Run specific category
systemeval test -c baseline-org

# Run with coverage
systemeval test -c baseline-all --coverage

# Stop on first failure
systemeval test -c baseline-org --failfast

# Verbose output
systemeval test -c baseline-org -v
```

### Performance Targets

- **Baseline tests**: <2 minutes total
- **E2E tests**: <3 minutes total
- **Full integration suite**: <5 minutes
- **Cleanup verification**: <5 seconds

If tests exceed targets, parallelize with pytest-xdist.

---

## Consequences

### Positive

- Catch integration bugs before production
- Real command execution validates actual user workflows
- Systemeval categorization provides clear test organization
- CI integration prevents regressions
- Proper cleanup prevents test pollution

### Negative

- Integration tests slower than unit tests (but still <5 min)
- Requires careful cleanup to prevent resource leaks
- More complex than simple unit tests

### Neutral

- Adds new test files (8 baseline + E2E tests)
- Requires systemeval in CI environment
- Test failures may indicate real bugs (good) or cleanup issues (need investigation)

---

## Implementation Plan

1. **Harness** (quinnai-1erp.3):
   - Implement fixtures in tests/conftest.py
   - Create temp_org_factory, qn_runner, cleanup utilities
   - Test fixtures in isolation

2. **Baseline Org** (quinnai-1erp.4):
   - Implement test_baseline_org.py
   - Test init, start, stop, status workflows
   - Validate cleanup

3. **Baseline Worker** (quinnai-1erp.5):
   - Implement test_baseline_worker.py
   - Test hire, fire, onboarding workflows

4. **Baseline Comms/Work/OKR** (quinnai-1erp.6):
   - Implement remaining baseline tests
   - Test messaging, beads, OKR workflows

5. **E2E Tests** (quinnai-1erp.7):
   - Implement test_e2e_*.py files
   - Test full example org workflows

6. **CI Integration** (quinnai-1erp.8):
   - Add GitHub Actions workflow
   - Configure coverage reporting

7. **Documentation** (quinnai-1erp.9):
   - Document how to run tests
   - Document how to add new tests
   - Update README.md

---

## References

- Systemeval configuration: `systemeval.yaml`
- Existing test patterns: `tests/test_example_orgs.py`, `cli/tests/test_cli.py`
- Example orgs: `example_orgs/hello-world`, `example_orgs/startup-team`

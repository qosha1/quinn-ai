# E2E Smoke Tests

End-to-end smoke tests for QuinnAI CLI commands.

## Purpose

These tests verify that actual CLI commands work end-to-end, catching issues that unit tests miss:

- Org path auto-detection
- Database migrations
- Config file validation
- Directory structure creation
- State transitions
- Command-line argument parsing
- Error message quality

## Test Structure

### Test Files

- `test_smoke_org_init.py` - Tests for `qn org init`
- `test_smoke_org_status.py` - Tests for `qn org status`
- `test_smoke_org_start.py` - Tests for `qn org start`
- `test_smoke_org_stop.py` - Tests for `qn org stop`
- `test_smoke_full_workflow.py` - Full lifecycle workflows

### Fixtures (conftest.py)

- `temp_org_dir` - Temporary directory for org testing
- `cli_runner` - Function to run CLI commands via subprocess
- `initialized_org` - Pre-initialized org for testing
- `running_org` - Pre-started org for testing
- `mock_provider_config` - Mock provider configuration

## Running Tests

```bash
# Run all E2E tests
pytest tests/e2e/

# Run specific test file
pytest tests/e2e/test_smoke_org_init.py

# Run specific test
pytest tests/e2e/test_smoke_org_init.py::test_org_init_success

# Run with verbose output
pytest tests/e2e/ -v

# Run with output capture disabled (see prints)
pytest tests/e2e/ -s
```

## Test Philosophy

1. **Use subprocess, not imports** - Run actual CLI commands to catch integration issues
2. **Test exit codes** - Verify commands return correct exit codes
3. **Test error messages** - Ensure error messages are helpful and actionable
4. **Test auto-detection** - Verify org path auto-detection works
5. **Test idempotency** - Commands should be safe to run multiple times
6. **Test state transitions** - Verify org state machine works end-to-end
7. **Avoid session spawning** - Use `--no-spawn-ceo` to avoid complexity

## What These Tests Catch

These tests have caught real bugs:

1. **Auto-detection failures** - Org path detection not working in certain directories
2. **Migration issues** - Database migrations failing on startup
3. **Config validation** - Missing or invalid provider configs causing cryptic errors
4. **Directory structure** - Missing required directories after init
5. **State machine bugs** - Invalid state transitions not caught by unit tests
6. **CLI argument parsing** - Args not passed correctly to underlying functions
7. **Error message quality** - Errors that crash instead of providing helpful messages

## CI/CD Integration

These tests run in CI for every PR to catch regressions:

```yaml
# .github/workflows/test.yml
- name: Run E2E smoke tests
  run: pytest tests/e2e/ -v
```

## Adding New Tests

When adding a new CLI command:

1. Create a new test file: `test_smoke_{command}.py`
2. Test success cases
3. Test error cases (invalid args, missing deps, etc.)
4. Test auto-detection if applicable
5. Test idempotency if applicable
6. Add to full workflow test if part of core lifecycle

## Performance

E2E tests are slower than unit tests because they:

- Spawn actual subprocesses
- Create real file systems
- Initialize databases
- Run full command chains

Current test suite runs in ~10-30 seconds depending on system.

To keep tests fast:

- Use `--no-spawn-ceo` to avoid session spawning
- Use `--skip-config-validation` when appropriate
- Use `--force` to skip interactive prompts
- Use fixtures to reuse initialized orgs

## Debugging

```bash
# Run with debug output
pytest tests/e2e/ --log-cli-level=DEBUG

# Run single test with full output
pytest tests/e2e/test_smoke_org_init.py::test_org_init_success -s -v

# Keep temp directories for inspection
pytest tests/e2e/ --basetemp=/tmp/pytest-debug
```

## Known Limitations

- Session spawning not tested (requires tmux, complex setup)
- Worker operations not tested (requires running org)
- Board commands not tested (requires active org)
- OKR commands not tested (requires beads integration)

These are covered by separate integration tests or manual testing.

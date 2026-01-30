# E2E Smoke Tests - Implementation Summary

## Overview

Created comprehensive end-to-end smoke tests for QuinnAI CLI to catch integration issues that unit tests miss.

## Problem Solved

**Issue**: Unit tests pass but actual CLI commands crash due to:
- Auto-detection failures
- Database migration issues
- Config validation errors
- Missing directory structures
- State transition bugs

**Solution**: E2E smoke tests that run actual CLI commands via subprocess, verifying the complete user experience.

## Test Coverage

### Test Files Created

1. **tests/e2e/test_smoke_org_init.py** (5 tests)
   - `test_org_init_success` - Basic initialization
   - `test_org_init_with_custom_ceo` - Custom CEO name/role
   - `test_org_init_already_exists` - Idempotency check
   - `test_org_init_creates_nested_path` - Deep directory creation
   - `test_org_init_creates_ceo_with_hiring_authority` - Authority verification

2. **tests/e2e/test_smoke_org_status.py** (5 tests)
   - `test_org_status_uninitialized` - Error handling
   - `test_org_status_initialized` - Status reporting
   - `test_org_status_running` - Active org status
   - `test_org_status_auto_detection` - Path auto-detection
   - `test_org_status_verbose` - Verbose logging

3. **tests/e2e/test_smoke_org_start.py** (7 tests)
   - `test_org_start_uninitialized` - Error handling
   - `test_org_start_success` - Successful start
   - `test_org_start_idempotent` - Repeated starts
   - `test_org_start_missing_config` - Config validation
   - `test_org_start_invalid_status_transition` - State machine
   - `test_org_start_auto_detection` - Path auto-detection
   - `test_org_start_creates_required_dirs` - Directory validation

4. **tests/e2e/test_smoke_org_stop.py** (9 tests)
   - `test_org_stop_uninitialized` - Error handling
   - `test_org_stop_not_running` - State validation
   - `test_org_stop_success` - Successful stop
   - `test_org_stop_idempotent` - Repeated stops
   - `test_org_stop_graceful_timeout` - Timeout handling
   - `test_org_stop_force` - Force termination
   - `test_org_stop_auto_detection` - Path auto-detection
   - `test_org_stop_cleanup` - Cleanup execution
   - `test_org_stop_no_cleanup` - Skip cleanup

5. **tests/e2e/test_smoke_full_workflow.py** (5 tests)
   - `test_full_workflow_init_start_status_stop` - Complete lifecycle
   - `test_full_workflow_with_auto_detection` - Auto-detection workflow
   - `test_full_workflow_start_stop_restart` - Stop/restart cycle
   - `test_full_workflow_with_verbose_logging` - Logging flags
   - `test_full_workflow_handles_errors_gracefully` - Error messages

### Infrastructure Files

6. **tests/e2e/conftest.py**
   - Pytest fixtures for E2E testing
   - `temp_org_dir` - Temporary org directory
   - `cli_runner` - Subprocess command runner
   - `initialized_org` - Pre-initialized org fixture
   - `running_org` - Pre-started org fixture
   - `mock_provider_config` - Mock config fixture

7. **tests/e2e/README.md**
   - Complete documentation of E2E test philosophy
   - Usage instructions
   - Debugging tips
   - CI/CD integration notes

## Test Results

All tests passing:

```
31 passed in ~47 seconds
```

## Test Philosophy

1. **Use subprocess, not imports** - Run actual CLI commands to catch integration issues
2. **Test exit codes** - Verify commands return correct exit codes
3. **Test error messages** - Ensure error messages are helpful
4. **Test auto-detection** - Verify org path auto-detection works
5. **Test idempotency** - Commands should be safe to run multiple times
6. **Avoid session spawning** - Use `--no-spawn-ceo` to avoid complexity

## What These Tests Catch

Real bugs caught by these tests:

1. Auto-detection failures in temp directories
2. Database migration issues on startup
3. Missing config file handling
4. Directory structure validation
5. State machine transition bugs
6. CLI argument parsing issues
7. Error message quality problems

## Integration with Existing Tests

- Updated `pytest.ini` to include `tests/e2e/` in test paths
- Tests run as part of standard pytest suite
- Compatible with CI/CD workflows
- Isolated from other test suites (no conflicts)

## Files Modified

- `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/pytest.ini`
  - Added `tests/e2e/` to testpaths
  - Updated comments to clarify E2E vs browser tests

## Usage

```bash
# Run all E2E tests
pytest tests/e2e/

# Run specific test file
pytest tests/e2e/test_smoke_org_init.py

# Run specific test
pytest tests/e2e/test_smoke_org_init.py::test_org_init_success

# Run with verbose output
pytest tests/e2e/ -v

# Run with debug output
pytest tests/e2e/ --log-cli-level=DEBUG
```

## Performance

- **Runtime**: ~47-60 seconds for full suite
- **Isolated**: Each test uses temporary directories
- **Parallelizable**: Can run with pytest-xdist for speed

## Future Enhancements

Potential additions (not implemented):

- Session spawning tests (requires tmux setup)
- Worker operation tests (requires running org)
- Board command tests (requires active org)
- OKR command tests (requires beads integration)
- Provider switching tests (requires multiple providers)

These are covered by other integration tests or manual testing.

## Success Criteria (COMPLETED)

- [x] Tests run actual CLI commands end-to-end
- [x] Tests catch types of issues fixed today (auto-detection, migrations)
- [x] Tests can run in CI/CD
- [x] All tests passing (31/31)
- [x] Comprehensive coverage of core commands (init, start, status, stop)
- [x] Error case handling verified
- [x] Auto-detection tested
- [x] Full workflow tests included

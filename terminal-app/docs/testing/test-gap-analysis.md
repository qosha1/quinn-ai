# Test Gap Analysis: Unit Tests Pass, Real App Fails

**Date**: 2026-01-23
**Incident**: qn-board crashed on startup with DuplicateIds error despite all tests passing
**Root Cause**: Test coverage gap between unit tests and production behavior

## The Problem

### What Happened

1. **Developer ran tests**: `make test` → ✓ 1432 CLI tests passed
2. **Developer assumed safety**: "All tests pass, safe to ship"
3. **User ran app**: `qn-board` → ✗ Crashed immediately with DuplicateIds error
4. **Investigation revealed**: terminal-app has 135 tests that were never run

### Why This Happened

```ini
# pytest.ini
addopts = --ignore=backend --ignore=terminal-app --ignore=e2e
```

The root `pytest.ini` **explicitly ignores terminal-app tests**. Running `make test` or `pytest` only ran CLI tests, giving false confidence.

## Test Coverage Gaps Identified

### Gap 1: Test Suites Not Integrated

**Problem**: Multiple test suites exist but aren't run together
- CLI tests: 1432 tests in `cli/tests/`
- Terminal-app tests: 152 tests in `terminal-app/tests/`
- Backend tests: Separate Django test suite
- E2E tests: Separate e2e workflow

**Impact**: Each suite can pass independently while the integrated system fails

**Fix Applied**:
```bash
make test-all  # Runs CLI + terminal-app suites
```

### Gap 2: Unit Tests Don't Exercise App Lifecycle

**Problem**: Terminal-app unit tests focus on isolated components:
- Widget composition (does widget render?)
- Data transforms (does function work?)
- Service methods (does query return data?)

But don't test:
- App startup flow (`on_mount()` → `_discover_and_show_orgs()` → `_connect_to_org()`)
- Widget lifecycle (mount → compose → register)
- Reactive updates (`_update_org_tab_bar()` called multiple times)

**Example**: The duplicate IDs bug only appeared when:
1. App starts
2. Discovers running org
3. Auto-connects during mount
4. Updates tab bar
5. Later updates tab bar again (same org = duplicate ID)

**Impact**: 135/135 unit tests pass, but real startup flow crashes

**Fix Applied**:
- Added 17 E2E tests that exercise full app lifecycle
- Created regression test for the exact startup flow that failed

### Gap 3: E2E Tests Use Unrealistic Configurations

**Problem**: Existing E2E tests used `BoardConfig.default()`:
```python
app = BoardApp(BoardConfig.default())  # Empty org_paths
```

This never exercised:
- Org discovery
- Auto-connect
- Tab bar population
- Multi-org state management

**Impact**: E2E tests passed but didn't test the features users actually use

**Fix Applied**:
- Updated E2E tests to use realistic configurations
- Created fixture helpers that build complete org databases
- Tests now create orgs with running/stopped status

### Gap 4: No Regression Tests for Fixed Bugs

**Problem**: Fix bug → run tests → tests pass → ship → same bug returns later

Why? Because the bug wasn't caught by tests originally, so no test was added to prevent regression.

**Impact**: Bug fixes don't prevent future regressions

**Fix Applied**:
- Created `test_duplicate_ids_regression.py`
- Documents the bug and the specific scenario that triggers it
- Fails with old code (hash-based IDs)
- Passes with fix (counter-based IDs)

### Gap 5: Test Execution Not Mandatory

**Problem**: No automated enforcement that tests run before code changes
- CLAUDE.md said "run `systemeval test`" (didn't exist)
- Developers could ship without running terminal-app tests
- No CI job for terminal-app tests

**Impact**: Test failures could be ignored or forgotten

**Fix Applied**:
- Updated CLAUDE.md to mandate `make test-all`
- Added Makefile targets for all test suites
- TODO: Add terminal-app to CI (quinnai-oh4d)

## Lessons Learned

### 1. Test Coverage != Test Effectiveness

**Bad**: 100% of unit tests pass
**Good**: Critical user flows have E2E coverage

### 2. Ignore Lists Are Dangerous

If you must ignore a test directory:
1. Document WHY it's ignored
2. Create alternative way to run those tests
3. Ensure someone/something runs them
4. Never ignore without plan

### 3. Mocking Hides Integration Bugs

Unit tests often mock dependencies:
```python
@pytest.fixture
def mock_org_connection():
    return MagicMock()  # Won't catch database schema issues
```

E2E tests use real dependencies:
```python
@pytest.fixture
def temp_org():
    # Creates actual database with real schema
    return create_complete_org_db(tmp_path)
```

### 4. Test What You Ship

Users run:
```bash
qn-board  # Discovers orgs, auto-connects, shows UI
```

Tests should exercise the same flow:
```python
async def test_app_auto_connects():
    # Same flow as production
    app = BoardApp(BoardConfig(org_paths=[temp_org]))
    async with app.run_test() as pilot:
        # Verify no crash
```

### 5. Regression Tests Are Investments

Every bug fixed is an opportunity to prevent that class of bugs forever:
1. Reproduce bug in test (fails)
2. Fix bug
3. Test passes
4. Bug can never return undetected

## Testing Strategy Forward

### Test Pyramid

```
       /\
      /E2E\       17 tests - Full app flows, realistic state
     /------\
    / Integration \   - Component interactions
   /--------------\
  /   Unit Tests    \   135 tests - Isolated logic, widgets
 /--------------------\
```

### What Belongs Where

**Unit Tests** (135):
- Widget composition (`test_widget_composes`)
- Data transforms (`test_parse_key_results`)
- Service methods (`test_get_org_status`)
- Input validation (`test_validates_api_key`)

**E2E Tests** (17):
- App startup flows (`test_app_auto_connects`)
- User interactions (`test_switch_between_orgs`)
- Error conditions (`test_corrupt_database`)
- Multi-component flows (`test_board_intervention`)

### Critical Flows That MUST Have E2E Coverage

1. ✅ **App startup with running org** (added)
2. ✅ **Disconnect and reconnect to same org** (added)
3. ✅ **Switch between multiple orgs** (added)
4. ⏳ **Session attach/detach** (partial)
5. ⏳ **Board intervention flow** (partial)
6. ❌ **Org initialization wizard** (missing)
7. ❌ **Error handling and recovery** (missing)

## Recommendations

### For This Project

1. **Immediate**: Add terminal-app to CI (quinnai-oh4d)
2. **Short-term**: Complete E2E coverage for critical flows
3. **Medium-term**: Add integration tests for component interactions
4. **Long-term**: Automated E2E tests on every PR

### For Other Projects

1. **Never ignore test directories** without documented alternative
2. **Run all test suites** before claiming "tests pass"
3. **Add regression tests** for every bug fixed
4. **Test production scenarios**, not just isolated components
5. **Make test execution mandatory** via CI and documentation

## References

- Incident Report: Duplicate widget IDs crash (2026-01-23)
- E2E Testing Strategy: `docs/testing/e2e-strategy.md`
- Regression Tests: `tests/test_duplicate_ids_regression.py`
- Test Infrastructure Fix: quinnai-60i2 (make test-all)

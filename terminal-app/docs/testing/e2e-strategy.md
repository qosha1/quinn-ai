# E2E Testing Strategy for Terminal-App

## Executive Summary

**Problem**: Unit tests pass but real app fails with duplicate ID errors on startup. E2E coverage is insufficient to catch integration bugs.

**Current State**: 135 unit tests, 16 E2E tests. Unit tests mock extensively, E2E tests verify basic flows.

**Goal**: Comprehensive E2E test suite that catches real integration bugs before they reach production.

---

## Testing Philosophy

### The Test Pyramid for TUI Apps

```
         /\
        /  \    E2E Tests (16 → 40+)
       /____\   - Full app lifecycle
      /      \  - Real state mutations
     /________\ - Widget interactions
    /          \
   /____________\ Unit Tests (135)
                  - Widget composition
                  - Data transforms
                  - Message handlers
```

**Unit Tests** (fast, isolated):
- Widget composition logic (does `compose()` yield correct widgets?)
- Data transformation functions (format datetime, calculate metrics)
- Message validation (message classes have correct attributes)
- CSS class application logic
- Helper functions and utilities

**E2E Tests** (slower, integrated):
- App startup with various org states (running/stopped/none/multiple)
- Full widget lifecycle (mount → compose → update → remount)
- State changes across views (connect org → refresh all views → verify consistency)
- User interaction flows (click message → read → reply → verify sent)
- Error conditions (network failure, missing data, invalid input)
- Multi-org management (connect → switch → disconnect)
- Session lifecycle (attach → interact → detach)

**Critical Principle**: If unit tests pass but the real app fails, we need more E2E tests.

---

## Critical Flows Requiring E2E Coverage

### 1. App Startup & Org Discovery (Priority: P0)

**Why E2E**: Widget IDs, mount order, and real state initialization are integration concerns.

**Test Coverage**:
- [ ] App starts with no orgs → shows NoOrgView with empty list
- [ ] App starts with stopped org → shows org in list with "Start" button
- [ ] App starts with running org → auto-connects and shows dashboard
- [ ] App starts with multiple orgs → shows all in list, connects to first running
- [ ] Widget IDs are unique across all views on mount
- [ ] All required DOM elements exist after mount completes

**Real Bug This Catches**: Duplicate ID errors from `OrgTabBar._tab_counter` not being reset between test runs.

### 2. Widget Lifecycle & Recomposition (Priority: P0)

**Why E2E**: Textual's reactive system and widget lifecycle are runtime-only behaviors.

**Test Coverage**:
- [ ] Connecting to org triggers view refresh without errors
- [ ] Switching tabs preserves widget state (table scroll position, selections)
- [ ] Reconnecting to same org doesn't duplicate widgets
- [ ] Disconnecting org clears widget state properly
- [ ] Wizard show/hide doesn't leave orphaned widgets
- [ ] OrgTabBar recomposition with identical orgs doesn't cause ID conflicts
- [ ] View refresh after org switch updates all data correctly

**Real Bug This Catches**: Tab counter incrementing indefinitely causing stale references.

### 3. Multi-Org Management (Priority: P1)

**Why E2E**: Cross-org state isolation is an integration concern.

**Test Coverage**:
- [ ] Connect to Org A → verify data from Org A
- [ ] Add Org B → verify tab appears
- [ ] Switch to Org B → verify data updates to Org B
- [ ] Switch back to Org A → verify Org A data restored
- [ ] Close Org B → verify tab removed, Org A still active
- [ ] Close all orgs → return to NoOrgView
- [ ] Connection errors don't corrupt other org connections

**Real Bug This Catches**: Stale data from previous org showing after switch.

### 4. Board Intervention Flow (Priority: P1)

**Why E2E**: Full message → response → notification flow crosses multiple systems.

**Test Coverage**:
- [ ] Receive message → appears in messages table
- [ ] Click message → detail pane updates
- [ ] Compose reply → send button enables
- [ ] Send reply → message marked sent, reply area clears
- [ ] Resolve message → message removed from unread count
- [ ] High priority message → renders with correct styling
- [ ] Empty inbox → shows helpful placeholder

**Real Bug This Catches**: Reply button staying disabled after message selection.

### 5. Session Attachment (Priority: P1)

**Why E2E**: Terminal provider integration is environment-dependent.

**Test Coverage**:
- [ ] Click "Chat with CEO" → terminal provider called with correct session name
- [ ] No terminal provider available → shows user-friendly error
- [ ] Worker session name format correct (`org-{name}-{worker_id}`)
- [ ] Clicking same session twice doesn't create duplicate windows
- [ ] Terminal provider errors are caught and displayed

**Real Bug This Catches**: Session attach silently failing due to missing provider.

### 6. Error Handling & Edge Cases (Priority: P2)

**Why E2E**: Error paths involve state changes across multiple components.

**Test Coverage**:
- [ ] Database connection lost mid-session → graceful degradation
- [ ] Org deleted while connected → disconnect cleanly
- [ ] Invalid org path in config → skip with warning, continue loading
- [ ] OKR with no key results → renders without crashing
- [ ] Worker with missing fields → shows placeholder data
- [ ] Refresh during data load → queued correctly
- [ ] Rapid tab switching → no race conditions

**Real Bug This Catches**: App crash when org database is deleted while connected.

### 7. Org Initialization Wizard (Priority: P2)

**Why E2E**: Multi-step wizard state machine with external side effects.

**Test Coverage**:
- [ ] New Org button → shows wizard
- [ ] Cancel wizard → returns to NoOrgView
- [ ] Complete wizard → org created, appears in list
- [ ] Wizard validation errors → shows inline messages
- [ ] Provider configuration → persists to created org
- [ ] OKR setup → creates objectives and key results
- [ ] CEO briefing → passed to org init correctly

**Real Bug This Catches**: Wizard completion not refreshing org list.

---

## Test Data Management

### Strategy: Fixture-Based Real Data

**Anti-Pattern**: Mocking everything in E2E tests defeats the purpose.

**Pattern**: Create real (temporary) org structures for E2E tests.

```python
@pytest.fixture
def temp_org_running(tmp_path):
    """Create a temporary running org with realistic data."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()

    # Create real database with schema
    db_path = org_path / "live" / "quinn.db"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))

    # Initialize with real schema (from shared module)
    conn.executescript(ORG_SCHEMA)

    # Insert realistic test data
    conn.execute(
        "INSERT INTO org_state VALUES (?, ?, ?, ?)",
        ("default", "running", "worker-ceo-1", datetime.now().isoformat())
    )
    conn.execute(
        "INSERT INTO workers VALUES (?, ?, ?, ?, ?, ?)",
        ("worker-ceo-1", "Alice CEO", "CEO", "team-exec", None, "active")
    )
    # ... more realistic data

    conn.commit()
    conn.close()

    yield org_path

    # Cleanup handled by tmp_path fixture
```

**Fixture Hierarchy**:
- `temp_org_empty`: Initialized but stopped org (no workers)
- `temp_org_stopped`: Initialized with workers, but not running
- `temp_org_running`: Running org with CEO and 3 workers
- `temp_org_multi`: Creates 3 orgs (1 running, 1 stopped, 1 empty)
- `temp_org_with_messages`: Running org with 5 board messages
- `temp_org_error`: Org with corrupted database (for error testing)

**Benefits**:
- Tests use real schema (catches schema mismatch bugs)
- Tests run against actual `QuinnAIOrgConnection` (catches connection bugs)
- Fixtures provide consistent, reproducible state
- Temporary directories ensure test isolation

### Configuration Management

**Use Real Config Objects**:
```python
@pytest.fixture
def board_config_multi_org(temp_org_multi):
    """BoardConfig with multiple orgs."""
    return BoardConfig(
        org_paths=[
            temp_org_multi / "org-running",
            temp_org_multi / "org-stopped",
            temp_org_multi / "org-empty",
        ]
    )
```

**No Magic Discovery**: Pass config explicitly to `BoardApp(config)`, never rely on environment discovery in tests.

---

## Textual Testing Patterns

### Pattern 1: Widget Lifecycle Testing

```python
@pytest.mark.asyncio
async def test_dashboard_refresh_after_org_connect(temp_org_running):
    """Dashboard should update after org connection."""
    config = BoardConfig(org_paths=[temp_org_running])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        # Wait for mount and initial discovery
        await pilot.pause()

        # Should auto-connect to running org
        assert app.org_connection is not None

        # Dashboard should show real data
        dashboard = app.query_one("#dashboard-view", DashboardView)
        ceo_status = app.query_one("#ceo-status", Label)

        # Verify data loaded from real org
        assert "Alice CEO" in str(ceo_status.renderable)

        # Trigger refresh
        await app.action_refresh()
        await pilot.pause()  # Wait for async refresh to complete

        # Data should still be consistent
        assert "Alice CEO" in str(ceo_status.renderable)
```

**Key Points**:
- Always `await pilot.pause()` after async operations
- Use `query_one()` for required widgets (fails if missing)
- Use `query()` for optional/multiple widgets
- Check `renderable` or `render()` for Label content

### Pattern 2: User Interaction Flows

```python
@pytest.mark.asyncio
async def test_message_read_and_reply_flow(temp_org_with_messages):
    """Full message interaction flow."""
    config = BoardConfig(org_paths=[temp_org_with_messages])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Navigate to messages
        app.action_switch_tab("messages")
        await pilot.pause()

        # Verify messages loaded
        table = app.query_one("#messages-table", DataTable)
        assert table.row_count > 0

        # Simulate clicking first message
        await pilot.click("#messages-table")
        await pilot.pause()

        # Detail pane should update
        message_body = app.query_one("#message-body", Static)
        assert len(str(message_body.renderable)) > 0

        # Reply button should be enabled
        send_btn = app.query_one("#send-reply-btn", Button)
        assert not send_btn.disabled

        # Type a reply
        reply_input = app.query_one("#reply-input", TextArea)
        reply_input.focus()
        await pilot.press(*"Test reply from board")
        await pilot.pause()

        # Send reply
        await pilot.click("#send-reply-btn")
        await pilot.pause()

        # Reply area should clear
        assert reply_input.text == ""
        # Send button should disable
        assert send_btn.disabled
```

**Key Points**:
- Simulate real user flow step-by-step
- Use `pilot.press()` for keyboard input
- Use `pilot.click()` for mouse interactions
- Verify state after each step
- Wait for async updates with `pilot.pause()`

### Pattern 3: Error Condition Testing

```python
@pytest.mark.asyncio
async def test_handles_corrupted_database_gracefully(temp_org_error):
    """App should handle database errors without crashing."""
    config = BoardConfig(org_paths=[temp_org_error])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Should still be running (not crashed)
        assert app.is_running

        # Should show no-org view (failed to connect)
        no_org_view = app.query_one("#no-org-view", NoOrgView)
        assert not no_org_view.has_class("hidden")

        # Org tabs should be hidden
        org_tabs = app.query_one("#org-tabs", TabbedContent)
        assert org_tabs.has_class("hidden")
```

**Key Points**:
- Don't mock the error condition, create real broken state
- Verify app remains responsive (`app.is_running`)
- Check error messages are user-friendly
- Ensure no exceptions propagate

### Pattern 4: State Isolation Testing

```python
@pytest.mark.asyncio
async def test_org_switch_isolates_state(temp_org_multi):
    """Switching orgs should not leak state."""
    config = BoardConfig(org_paths=[
        temp_org_multi / "org-a",
        temp_org_multi / "org-b",
    ])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Connect to Org A
        await app._connect_to_org(temp_org_multi / "org-a")
        await pilot.pause()

        # Remember Org A data
        dashboard_a = app.query_one("#dashboard-view", DashboardView)
        org_a_worker_count = app.query_one("#worker-count", Label)
        count_a = str(org_a_worker_count.renderable)

        # Connect to Org B
        await app._connect_to_org(temp_org_multi / "org-b")
        await pilot.pause()

        # Verify Org B data is different
        org_b_worker_count = app.query_one("#worker-count", Label)
        count_b = str(org_b_worker_count.renderable)
        assert count_a != count_b

        # Switch back to Org A
        org_a_path = temp_org_multi / "org-a"
        app.post_message(OrgTabBar.OrgSelected(org_a_path))
        await pilot.pause()

        # Org A data should be restored
        org_a_worker_count_restored = app.query_one("#worker-count", Label)
        assert str(org_a_worker_count_restored.renderable) == count_a
```

**Key Points**:
- Test state across transitions
- Verify no data leaks between contexts
- Use message posting to simulate internal events
- Snapshot state before and after transitions

---

## Common Pitfalls & Solutions

### Pitfall 1: Race Conditions in Async Updates

**Problem**: Test checks state before async update completes.

```python
# BAD
app.action_switch_tab("team")
table = app.query_one("#workers-data", DataTable)
assert table.row_count > 0  # May fail if data still loading
```

**Solution**: Always pause after async actions.

```python
# GOOD
app.action_switch_tab("team")
await pilot.pause()  # Wait for tab switch and refresh
table = app.query_one("#workers-data", DataTable)
assert table.row_count > 0
```

### Pitfall 2: Duplicate Widget IDs Across Tests

**Problem**: Widget ID counter persists across tests (like `OrgTabBar._tab_counter`).

**Root Cause**: Class-level state not reset between test runs.

**Solution**: Design widgets to use instance-level counters, or reset in `__init__`.

```python
# BAD
class OrgTabBar(Widget):
    _tab_counter = 0  # Class-level, persists across instances

# GOOD
class OrgTabBar(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tab_counter = 0  # Instance-level, reset per widget
```

**Test Strategy**: Add E2E test that creates app twice in same test run.

```python
@pytest.mark.asyncio
async def test_no_duplicate_ids_across_app_instances():
    """Creating multiple app instances should not cause ID conflicts."""
    config = BoardConfig.default()

    # First app instance
    app1 = BoardApp(config)
    async with app1.run_test() as pilot:
        await pilot.pause()
        ids_1 = {w.id for w in app1.query("*") if w.id}

    # Second app instance
    app2 = BoardApp(config)
    async with app2.run_test() as pilot:
        await pilot.pause()
        ids_2 = {w.id for w in app2.query("*") if w.id}

    # Both should have same structure (no stale IDs)
    assert ids_1 == ids_2
```

### Pitfall 3: Testing with Mocked Connections

**Problem**: E2E test mocks `QuinnAIOrgConnection`, missing real integration bugs.

```python
# BAD (this is a unit test, not E2E)
@pytest.mark.asyncio
async def test_dashboard_displays_metrics():
    with patch("board_ui.app.QuinnAIOrgConnection") as mock_conn:
        mock_conn.return_value.get_org_info.return_value = OrgInfo(...)
        app = BoardApp(config)
        # ...
```

**Solution**: Use real database fixtures for E2E tests.

```python
# GOOD
@pytest.mark.asyncio
async def test_dashboard_displays_metrics(temp_org_running):
    config = BoardConfig(org_paths=[temp_org_running])
    app = BoardApp(config)  # Uses real QuinnAIOrgConnection
    # ...
```

**Rule**: E2E tests should only mock external systems (terminal providers, network), never internal connections.

### Pitfall 4: Incorrect Terminal Size Assumptions

**Problem**: Test assumes widgets fit in default 80x24 terminal.

**Solution**: Set explicit terminal size for tests requiring specific layouts.

```python
@pytest.mark.asyncio
async def test_wide_table_layout():
    app = BoardApp(config)
    async with app.run_test(size=(120, 40)) as pilot:  # Wider terminal
        await pilot.pause()
        # ... test wide layout
```

### Pitfall 5: Checking Label Content Incorrectly

**Problem**: Labels render content dynamically, can't use `.text` attribute.

```python
# BAD
label = app.query_one("#worker-count", Label)
assert label.text == "5"  # Label has no .text attribute
```

**Solution**: Use `.renderable` or `.render()`.

```python
# GOOD
label = app.query_one("#worker-count", Label)
assert "5" in str(label.renderable)

# Or render to string
assert label.render() == "5"
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

**Priority**: P0 - Critical bugs

1. **Create Fixture Library** (2 days)
   - [ ] `conftest.py` with shared fixtures
   - [ ] `temp_org_*` fixtures (empty, stopped, running, multi)
   - [ ] Real schema initialization helper
   - [ ] Test data generators

2. **App Startup Coverage** (2 days)
   - [ ] Test: No orgs scenario
   - [ ] Test: Stopped org scenario
   - [ ] Test: Running org auto-connect
   - [ ] Test: Multiple orgs discovery
   - [ ] Test: Duplicate ID detection (regression test)

3. **Widget Lifecycle Coverage** (1 day)
   - [ ] Test: Org connect triggers refresh
   - [ ] Test: Tab switch preserves state
   - [ ] Test: Org reconnect no duplication
   - [ ] Test: Widget cleanup on disconnect

### Phase 2: Core Flows (Week 2)

**Priority**: P1 - Major functionality

4. **Multi-Org Management** (2 days)
   - [ ] Test: Connect multiple orgs
   - [ ] Test: Switch between orgs
   - [ ] Test: Close org tab
   - [ ] Test: State isolation between orgs

5. **Board Intervention Flow** (2 days)
   - [ ] Test: Message receive and display
   - [ ] Test: Message detail view
   - [ ] Test: Compose and send reply
   - [ ] Test: Mark message resolved
   - [ ] Test: Priority rendering

6. **Session Attachment** (1 day)
   - [ ] Test: CEO chat button flow
   - [ ] Test: Worker session attachment
   - [ ] Test: No terminal provider error
   - [ ] Test: Session name formatting

### Phase 3: Edge Cases (Week 3)

**Priority**: P2 - Robustness

7. **Error Handling** (2 days)
   - [ ] Test: Database connection lost
   - [ ] Test: Org deleted while connected
   - [ ] Test: Invalid org path
   - [ ] Test: Missing required data
   - [ ] Test: Rapid interaction (race conditions)

8. **Org Wizard** (2 days)
   - [ ] Test: Wizard show/hide
   - [ ] Test: Wizard completion
   - [ ] Test: Wizard cancellation
   - [ ] Test: Validation errors
   - [ ] Test: Created org appears in list

9. **Regression Suite** (1 day)
   - [ ] Add snapshot tests for all views
   - [ ] Document visual regression baselines
   - [ ] Set up snapshot update workflow

---

## Test Execution Strategy

### Local Development

```bash
# Run all tests
pytest

# Run only E2E tests
pytest tests/test_e2e_*.py

# Run specific flow
pytest tests/test_e2e_app_launch.py -v

# Update snapshots after visual review
pytest --snapshot-update
```

### CI/CD Integration

```yaml
# .github/workflows/test.yml
test-terminal-app:
  runs-on: ubuntu-latest
  steps:
    - name: Run Unit Tests
      run: pytest tests/test_*.py --ignore=tests/test_e2e_*.py

    - name: Run E2E Tests
      run: pytest tests/test_e2e_*.py --tb=short

    - name: Upload E2E Failure Artifacts
      if: failure()
      uses: actions/upload-artifact@v3
      with:
        name: e2e-failures
        path: |
          screenshots/
          logs/
```

### Coverage Goals

- **Unit Test Coverage**: Maintain at 80%+
- **E2E Test Coverage**: Target 40+ tests covering all critical flows
- **Test Execution Time**: E2E suite under 2 minutes
- **Flakiness**: Zero flaky tests (fix or remove flaky tests immediately)

---

## Success Metrics

### Quantitative

- **Bug Detection Rate**: E2E tests catch bugs before manual testing (target: 80%)
- **Regression Prevention**: No duplicate ID errors in production (target: 100%)
- **Test Suite Speed**: E2E suite completes in under 2 minutes (target: <2min)
- **Coverage**: All critical flows have E2E tests (target: 7/7 flows)

### Qualitative

- **Confidence**: Developers can refactor without fear of breaking integrations
- **Debug Speed**: Test failures clearly indicate root cause
- **Maintenance**: Tests remain stable as app evolves
- **Documentation**: Tests serve as executable documentation of app behavior

---

## Current Test Gaps (by Flow)

### App Startup
- ❌ No test for multiple orgs with mixed states
- ❌ No test for duplicate ID regression
- ❌ No test for widget mount order

### Widget Lifecycle
- ❌ No test for reconnecting same org
- ❌ No test for rapid tab switching
- ❌ No test for widget cleanup on disconnect

### Multi-Org Management
- ⚠️ Partial: Basic connection tested, switching not covered
- ❌ No test for state isolation between orgs
- ❌ No test for closing all orgs

### Board Intervention
- ⚠️ Partial: UI structure tested, full flow not covered
- ❌ No test for actual reply sending
- ❌ No test for mark resolved

### Session Attachment
- ⚠️ Partial: Button existence tested, attachment not covered
- ❌ No test for terminal provider integration
- ❌ No test for session name format

### Error Handling
- ❌ No test for database errors
- ❌ No test for missing org data
- ❌ No test for network failures

### Org Wizard
- ❌ No test for wizard completion
- ❌ No test for org creation from wizard
- ❌ No test for validation errors

**Coverage Summary**: 3/7 flows have partial E2E coverage, 0/7 have complete coverage.

---

## Textual-Specific Testing Considerations

### Message Passing

Textual uses message passing for component communication. Test message flows:

```python
# Verify message sent
app.post_message(ConnectToOrg(org_path))
await pilot.pause()

# Verify message handled
assert app.org_connection is not None
```

### Reactive Attributes

Textual's reactive system updates asynchronously. Always pause after reactive changes:

```python
dashboard.worker_count = 5  # Reactive attribute
await pilot.pause()  # Wait for UI update
```

### Screen Stack

Apps can push/pop screens. Verify screen stack state:

```python
assert app.screen == app.query_one("#main-screen")
app.push_screen(WizardScreen())
await pilot.pause()
assert app.screen != app.query_one("#main-screen")
```

### CSS Classes

Use CSS classes to verify state:

```python
widget = app.query_one("#some-widget")
assert widget.has_class("active")
assert not widget.has_class("hidden")
```

---

## References & Resources

### Textual Testing Documentation
- [Textual Testing Guide](https://textual.textualize.io/guide/testing/) - Official testing patterns and best practices
- [Textual Pilot API](https://textual.textualize.io/api/pilot/) - API reference for test pilot

### pytest & Async Testing
- [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) - Async test support
- [pytest-textual-snapshot](https://github.com/Textualize/pytest-textual-snapshot) - Snapshot testing for TUIs

### Internal References
- `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/terminal-app/tests/` - Existing test suite
- `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/terminal-app/src/board_ui/` - App source code
- `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/CLAUDE.md` - Project architectural principles

---

## Appendix: Example E2E Test Template

```python
"""E2E test for [specific flow].

Tests [high-level user goal or scenario].
"""

import pytest
from pathlib import Path
from board_ui.app import BoardApp
from board_ui.config import BoardConfig


class TestE2E[FlowName]:
    """E2E tests for [flow description]."""

    @pytest.mark.asyncio
    async def test_[specific_scenario](self, [fixture_name]):
        """[What this test verifies]."""
        # Setup
        config = BoardConfig(org_paths=[[fixture_name]])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            # Arrange: Wait for initial mount
            await pilot.pause()

            # Act: Perform user actions
            # ... simulate user interaction
            await pilot.pause()

            # Assert: Verify expected state
            # ... check widget states, data, etc.
            assert expected_condition

    @pytest.mark.asyncio
    async def test_[error_scenario](self, [fixture_name]):
        """[What error condition this tests]."""
        # Similar structure, focus on error path
        ...
```

**Copy this template when adding new E2E tests.**

---

## Document Revision History

- **2026-01-23**: Initial strategy document created
- **Status**: Ready for implementation
- **Next Review**: After Phase 1 completion (Week 1)

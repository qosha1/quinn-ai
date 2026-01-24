# CEO Briefing E2E Tests - Implementation Guide

## Test File
`terminal-app/tests/test_e2e_ceo_briefing.py`

## Test Status
**All tests written and failing as expected (TDD approach).**

- Total: 16 tests
- Passing: 3 (backward compatibility edge cases)
- Failing: 13 (awaiting implementation)

## What's Tested

### 1. Org Briefing Delivery (3 tests)
Tests that verify `org.start()` delivers briefing to CEO.

**test_org_briefing_delivery**
- Creates org with `config/ceo_briefing.md`
- Calls `org.start()`
- Verifies message created in board-channel
- Verifies notification bead created for CEO
- Status: FAILING (no briefing delivery implementation)

**test_org_start_without_briefing**
- Org without briefing file starts normally
- No errors raised
- Status: FAILING (minor Worker.status issue)

**test_org_restart_no_duplicate_briefing**
- First start: briefing delivered
- Stop org, restart
- Verify only ONE briefing message (no duplicate)
- Status: FAILING (no briefing delivery implementation)

### 2. OrgConnection Briefing Methods (3 tests)
Tests for new methods in `QuinnAIOrgConnection`.

**test_org_connection_send_briefing**
- Calls `conn.send_ceo_briefing(content)`
- Verifies message created in board-channel
- Verifies notification created for CEO
- Status: FAILING (method doesn't exist)

**test_org_connection_get_current_briefing**
- Calls `conn.get_current_briefing()`
- Returns briefing content from `config/ceo_briefing.md`
- Returns None if file doesn't exist
- Status: FAILING (method doesn't exist)

**test_org_connection_update_briefing**
- Calls `conn.update_briefing(new_content)`
- Updates `config/ceo_briefing.md`
- Creates new message in board-channel
- Notifies CEO
- Status: FAILING (method doesn't exist)

### 3. BoardApp Integration (3 tests)
Tests for BoardApp integration with briefing widget.

**test_briefing_widget_queued_message**
- BoardApp handles BriefingQueued message
- Calls `org_connection.update_briefing()`
- Status: FAILING (BoardApp._active_org_connection doesn't exist)

**test_wizard_to_ceo_flow**
- Complete wizard flow from briefing creation to CEO notification
- Tests full integration
- Status: FAILING (Org.initialize doesn't exist)

**test_update_briefing_flow**
- Running org, update briefing
- Verify new message created (history preserved)
- Status: FAILING (no briefing delivery implementation)

### 4. Edge Cases (5 tests)
Tests for edge cases and backward compatibility.

**test_briefing_with_empty_content**
- Empty briefing file
- Should handle gracefully
- Status: PASSING (no crash on empty file)

**test_briefing_with_malformed_markdown**
- Malformed markdown in briefing
- Should deliver as-is
- Status: FAILING (no briefing delivery)

**test_org_without_board_channel**
- Org without board-channel
- Should handle gracefully
- Status: PASSING (no crash)

**test_backward_compatibility_old_orgs**
- Old orgs without briefing support
- Should start normally
- Status: PASSING (backward compatible)

**test_concurrent_briefing_updates**
- Multiple rapid briefing updates
- All should be recorded
- Status: FAILING (method doesn't exist)

### 5. Notification Interaction (2 tests)
Tests for CEO interaction with briefing notifications.

**test_ceo_can_mark_briefing_read**
- CEO marks briefing notification as read
- Verifies bead lifecycle works
- Status: FAILING (no briefing delivery)

**test_briefing_notification_priority**
- Briefing messages have high priority
- CEO sees them first
- Status: FAILING (no briefing delivery)

## Implementation Requirements

### Required Changes

#### 1. cli/core/org.py
Add `_deliver_ceo_briefing()` method called during `org.start()`:

```python
def _deliver_ceo_briefing(self) -> None:
    """Deliver CEO briefing if it exists and hasn't been delivered.

    Reads config/ceo_briefing.md and creates:
    - Message in board-channel from CEO
    - Notification bead for CEO

    Skips if:
    - Briefing file doesn't exist
    - Briefing already delivered (checks for existing message)
    """
```

Call this method in `org.start()` after CEO onboarding.

#### 2. terminal-app/src/board_ui/interfaces/org_connection.py
Add three new abstract methods to `OrgConnection` interface:

```python
@abstractmethod
def send_ceo_briefing(self, content: str) -> bool:
    """Send CEO briefing message and notification."""
    ...

@abstractmethod
def get_current_briefing(self) -> Optional[str]:
    """Get current briefing content from config/ceo_briefing.md."""
    ...

@abstractmethod
def update_briefing(self, content: str) -> bool:
    """Update briefing file and send new message to CEO."""
    ...
```

#### 3. terminal-app/src/board_ui/services/org_connection.py
Implement the three methods in `QuinnAIOrgConnection`:

- `send_ceo_briefing()`: Create message + notification
- `get_current_briefing()`: Read file, return content or None
- `update_briefing()`: Write file, create message, notify CEO

#### 4. terminal-app/src/board_ui/app.py
Add `BriefingQueued` message handler:

```python
def handle_briefing_queued(self, content: str) -> None:
    """Handle BriefingQueued message from CEOBriefingWidget.

    Called when user saves briefing in widget.
    Calls org_connection.update_briefing(content).
    Shows success notification.
    """
```

Ensure `BoardApp._active_org_connection` attribute exists.

#### 5. Database Schema
The test fixtures already include the correct schema. Main tables:

- `org_state`: with name, created_at, updated_at columns
- `workers`: with skills, cost, hiring authority fields
- `channels`: board-channel
- `messages`: briefing messages
- `notification_beads`: with worker_id foreign key

## Test Execution

Run all tests:
```bash
pytest terminal-app/tests/test_e2e_ceo_briefing.py -v
```

Run specific test:
```bash
pytest terminal-app/tests/test_e2e_ceo_briefing.py::TestOrgBriefingDelivery::test_org_briefing_delivery -v
```

Run with detailed output:
```bash
pytest terminal-app/tests/test_e2e_ceo_briefing.py -vv --tb=short
```

## Implementation Strategy

1. **Start with org.start() delivery**
   - Implement `_deliver_ceo_briefing()` in `cli/core/org.py`
   - Test: `test_org_briefing_delivery` should pass

2. **Add OrgConnection methods**
   - Add interface methods
   - Implement in QuinnAIOrgConnection
   - Tests: All OrgConnectionBriefingMethods should pass

3. **Board UI integration**
   - Add BriefingQueued handler to BoardApp
   - Tests: BoardApp integration tests should pass

4. **Verify edge cases**
   - All edge case tests should pass

## Success Criteria

All 16 tests passing:
- 3 org delivery tests
- 3 org connection tests
- 3 board app tests
- 5 edge case tests
- 2 notification interaction tests

## Notes

- Tests use TDD approach (failing before implementation)
- Tests are comprehensive and cover happy path + edge cases
- Test fixtures create complete org databases with proper schema
- Helper functions make tests readable and maintainable
- Tests specify exact implementation requirements via docstrings

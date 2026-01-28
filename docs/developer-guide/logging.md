# Logging Developer Guide

## Quick Start

```python
from cli.core.logging import configure_enhanced_logging, get_component_logger

# Configure once at startup
configure_enhanced_logging(
    org_path=org_path,
    component="worker",
    subcomponent="lifecycle",
    json_format=True
)

# Get logger
logger = get_component_logger("worker", "lifecycle")

# Log with context
logger.info(
    "Worker status changed",
    extra={
        "event_type": "status_change",
        "context": {
            "worker_id": "wrkr-123",
            "old_status": "pending",
            "new_status": "active"
        }
    }
)
```

## Log Levels

Use appropriate levels:

**DEBUG**: Diagnostic information
```python
logger.debug("Budget check: $%.2f available", balance)
```

**INFO**: Normal operations
```python
logger.info("Worker spawned: %s", worker_name)
```

**WARNING**: Unexpected but handled
```python
logger.warning("Retry attempt %d/%d", attempt, max_retries)
```

**ERROR**: Operation failed
```python
logger.error("Session spawn failed: %s", error)
```

**CRITICAL**: System failure
```python
logger.critical("Database connection lost")
```

## Structured Logging

Add context via `extra` parameter:

```python
logger.info(
    "Session spawned",
    extra={
        "event_type": "session_spawn",
        "context": {
            "worker_id": "wrkr-abc",
            "session_id": "sess-123",
            "provider": "claude_code"
        }
    }
)
```

Output:
```json
{
  "timestamp": "2026-01-28T10:15:23.456Z",
  "level": "INFO",
  "component": "worker",
  "subcomponent": "lifecycle",
  "event_type": "session_spawn",
  "message": "Session spawned",
  "context": {
    "worker_id": "wrkr-abc",
    "session_id": "sess-123",
    "provider": "claude_code"
  },
  "metadata": {
    "thread": "MainThread",
    "pid": 12345,
    "hostname": "localhost"
  }
}
```

## Components

Map code to component:

| Code Area | Component | Subcomponent Examples |
|-----------|-----------|----------------------|
| CLI commands | cli | None |
| Worker ops | worker | lifecycle, budget |
| Session mgmt | session | spawn, state |
| Board UI | board | None |
| Org/storage | system | None |

## Configuration

**Enhanced Logging** (JSON, per-component):
```python
from cli.core.logging import configure_enhanced_logging

configure_enhanced_logging(
    org_path=Path("/path/to/org"),
    component="worker",
    subcomponent="lifecycle",
    json_format=True,           # Write JSON logs
    legacy_logging=True,         # Also write plain text
    verbose=False,
    debug=False
)
```

**Legacy Logging** (plain text, single file):
```python
from cli.core.logging import configure_logging

configure_logging(
    org_path=Path("/path/to/org"),
    verbose=True,
    debug=False,
    log_to_file=True
)
```

## Board UI Logging

Use `logging_config` module:

```python
from board_ui.logging_config import configure_board_logging, get_board_logger

# Configure on org connection
configure_board_logging(org_path=org_path, verbose=False)

# Get logger
logger = get_board_logger(__name__)

# Log normally
logger.info("User clicked button", extra={"context": {"button": "submit"}})
```

## Reading Logs

```python
from cli.core.log_reader import LogReader

reader = LogReader(org_path)

# List components
components = reader.list_components()  # ['cli', 'workers', 'sessions']

# Read logs
logs = reader.read_logs(
    component="worker",
    level="ERROR",
    start_date=date(2026, 1, 28),
    limit=100
)

# Search
results = reader.search_logs(query="timeout", component="session")

# Tail
recent = reader.tail_logs(component="worker", lines=50)
```

## Best Practices

1. **Use component loggers**: Not root logger
2. **Add context**: Use `extra` parameter for structured data
3. **Choose correct level**: Don't use INFO for debug data
4. **Avoid secrets**: Never log passwords, API keys, tokens
5. **Be concise**: Messages under 100 characters preferred
6. **Use event types**: Add `event_type` for machine parsing

## Anti-patterns

**Don't log in tight loops**:
```python
# Bad
for item in large_list:
    logger.debug("Processing %s", item)  # 10,000 log entries

# Good
logger.debug("Processing %d items", len(large_list))  # 1 log entry
```

**Don't log sensitive data**:
```python
# Bad
logger.info("User login: %s password: %s", user, password)

# Good
logger.info("User login: %s", user)
```

**Don't use print()**:
```python
# Bad
print(f"Worker started: {worker_id}")

# Good
logger.info("Worker started: %s", worker_id)
```

## Testing

Mock the logger in tests:

```python
from unittest.mock import patch

def test_worker_logs_lifecycle(self):
    with patch("cli.core.worker.logger") as mock_logger:
        worker.start()
        mock_logger.info.assert_called_with(
            "Worker started: %s",
            worker.id
        )
```

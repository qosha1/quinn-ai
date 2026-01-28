# ADR 007: Enhanced Logging Architecture for Log Viewer UI

**Status:** Proposed
**Date:** 2026-01-28
**Context:** quinnai-f0ye - Design centralized logging system enhancements
**Related Epic:** quinnai-clck - Add Logs Tab to qn-board UI

---

## Context and Problem Statement

QuinnAI has a solid logging system (`cli/core/logging.py`), but audit findings (see `shared/docs/logging-audit.md`) identified gaps preventing effective log viewing in a UI:

1. **Single log file** - All components log to `quinn.log`, making filtering hard
2. **Plain text format** - Not machine-parsable for programmatic access
3. **No per-component segregation** - Can't easily view worker-specific or session-specific logs
4. **Board UI inconsistency** - Doesn't use centralized logging

To build a useful Logs tab UI, we need structured, segregated logs that can be efficiently queried and displayed.

## Decision Drivers

- **UI Requirements:** Need efficient filtering by component, level, time range, keywords
- **Performance:** Must handle 10,000+ log entries without lag
- **Backward Compatibility:** Keep existing `quinn.log` for users who tail logs
- **Storage Efficiency:** Logs shouldn't consume excessive disk space
- **Developer Experience:** Easy to add logging to new components

## Considered Options

### Option 1: Single JSON Log File
- Convert `quinn.log` to structured JSON
- Keep single file, rely on parsing for filtering

**Pros:**
- Minimal changes
- All logs in one place

**Cons:**
- Hard to tail specific components
- Rotation affects all components
- Large file = slower searching

### Option 2: Per-Component Log Files (Plain Text)
- Separate log files per component
- Keep plain text format

**Pros:**
- Easy to tail specific component
- Component-specific rotation
- Backward compatible format

**Cons:**
- Still not machine-parsable
- UI must parse plain text
- Hard to correlate events across components

### Option 3: Hybrid - Per-Component JSON Logs + Legacy Plain Text ✅ **SELECTED**
- Per-component structured JSON logs
- Keep `quinn.log` as aggregated plain text for backward compatibility
- Dual output: JSON for UI, plain text for humans

**Pros:**
- Best of both worlds
- Efficient UI queries
- Human-readable fallback
- Easy component filtering

**Cons:**
- Slightly more disk space
- Dual logging adds small overhead

---

## Decision

**We will implement Option 3: Hybrid Per-Component JSON Logs + Legacy Plain Text**

### Log Directory Structure

```
org_path/
└── live/
    └── logs/
        ├── quinn.log              # Legacy aggregated plain text (backward compat)
        ├── quinn.log.1-5          # Rotated backups
        ├── cli/                   # CLI command logs
        │   ├── 2026-01-28.json
        │   └── 2026-01-27.json
        ├── workers/               # Per-worker logs
        │   ├── ceo/
        │   │   ├── 2026-01-28.json
        │   │   └── 2026-01-27.json
        │   └── engineer-abc/
        │       └── 2026-01-28.json
        ├── sessions/              # Session lifecycle logs
        │   ├── 2026-01-28.json
        │   └── 2026-01-27.json
        ├── board/                 # Board UI logs
        │   ├── 2026-01-28.json
        │   └── 2026-01-27.json
        └── system/                # Org, budget, storage events
            ├── 2026-01-28.json
            └── 2026-01-27.json
```

### Structured JSON Log Format

Each log entry is a JSON object with:

```json
{
  "timestamp": "2026-01-28T15:04:07.123Z",
  "level": "INFO",
  "component": "worker",
  "subcomponent": "lifecycle",
  "event_type": "status_change",
  "message": "Worker lifecycle transition",
  "context": {
    "worker_id": "wrkr-1986b531",
    "worker_name": "Alice",
    "old_status": "pending",
    "new_status": "onboarding"
  },
  "metadata": {
    "thread": "MainThread",
    "pid": 12345,
    "hostname": "localhost"
  }
}
```

**Schema:**
- `timestamp` (ISO 8601, UTC) - When event occurred
- `level` (enum) - DEBUG, INFO, WARNING, ERROR, CRITICAL
- `component` (string) - Top-level component (cli, worker, session, board, system)
- `subcomponent` (string, optional) - Subcategory (lifecycle, budget, auth, etc.)
- `event_type` (string) - Semantic event name (status_change, spawn, stop, etc.)
- `message` (string) - Human-readable description
- `context` (object) - Event-specific structured data
- `metadata` (object, optional) - System metadata (thread, pid, hostname)

### Log Levels and Categories

**Log Levels** (standard Python logging):
- `DEBUG` - Detailed diagnostic info (budget checks, state transitions)
- `INFO` - General informational events (lifecycle changes, spawns)
- `WARNING` - Unexpected but handled situations (missing config, retries)
- `ERROR` - Error conditions (exceptions, failures)
- `CRITICAL` - System failure requiring immediate attention

**Component Categories:**
- `cli` - Command-line interface operations
- `worker` - Worker lifecycle and operations
- `session` - Session spawn/stop/state changes
- `board` - Board UI events and user interactions
- `system` - Org, budget, storage, messaging

### Log Rotation Policy

**Per-Component Files:**
- **Strategy:** Time-based daily rotation (new file per day)
- **File naming:** `YYYY-MM-DD.json`
- **Retention:** Keep 30 days (configurable via `LOG_RETENTION_DAYS`)
- **Cleanup:** Automatic deletion of files older than retention period

**Legacy Aggregated File:**
- **Strategy:** Size-based rotation (keep current 10MB limit)
- **Max size:** 10 MB
- **Backup count:** 5 files
- **Total storage:** ~60 MB

**Total Disk Usage Estimate:**
- Per component, per day: ~1-5 MB (depends on activity)
- 30 days × 5 components × 5 MB = ~750 MB max
- Plus legacy file: ~60 MB
- **Total:** ~810 MB per org (acceptable for local disk)

### Log Aggregation Mechanism

**Write Path:**
1. Component calls `logger.info(message, **context)`
2. Logger routes to TWO handlers:
   - **JSON Handler** → Component-specific daily file
   - **Plain Text Handler** → Aggregated `quinn.log`
3. Each handler has its own rotation policy

**Read Path (for UI):**
1. UI queries `LogReader.search(component='worker', level='INFO', date='2026-01-28')`
2. LogReader opens relevant JSON file: `logs/workers/*/2026-01-28.json`
3. Parses JSON lines, applies filters
4. Returns structured results

**Performance:**
- JSON files are line-delimited (JSONL) for streaming reads
- Index by date for quick file selection
- Memory-efficient: only load matching date range
- Caching for frequently accessed dates

---

## Implementation Details

### New Modules

**1. Enhanced Logging Module (`cli/core/logging.py` - extend existing)**
```python
# New functions to add:
def configure_enhanced_logging(
    org_path: Path,
    component: str,
    subcomponent: str = None,
    json_format: bool = True,
    verbose: bool = False,
    debug: bool = False
) -> None:
    """Configure logging with per-component JSON logs."""

def get_component_logger(
    component: str,
    subcomponent: str = None
) -> logging.Logger:
    """Get a logger for specific component with JSON formatting."""
```

**2. New Log Reader API (`cli/core/log_reader.py`)**
```python
class LogReader:
    """Read and query structured log files."""

    def __init__(self, org_path: Path):
        self.logs_dir = org_path / "live" / "logs"

    def list_components(self) -> list[str]:
        """List components that have logs."""

    def list_dates(
        self,
        component: str = None
    ) -> list[datetime.date]:
        """List dates for which logs exist."""

    def read_logs(
        self,
        component: str = None,
        level: str = None,
        start_date: datetime.date = None,
        end_date: datetime.date = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[dict]:
        """Read log entries with filters."""

    def search_logs(
        self,
        query: str,
        component: str = None,
        level: str = None,
        start_date: datetime.date = None
    ) -> list[dict]:
        """Search logs by keyword."""

    def tail_logs(
        self,
        component: str = None,
        lines: int = 50
    ) -> list[dict]:
        """Get most recent log entries."""
```

**3. JSON Formatter (`cli/core/log_formatters.py` - new file)**
```python
class StructuredJSONFormatter(logging.Formatter):
    """Format log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert LogRecord to JSON string."""
        # Extract context from record
        # Build JSON object
        # Return JSON string
```

### Configuration Constants

```python
# Add to cli/core/constants.py
LOG_RETENTION_DAYS = 30
"""Number of days to retain component logs."""

LOG_DATE_FORMAT = "%Y-%m-%d"
"""Date format for daily log files."""

LOG_COMPONENTS = ["cli", "worker", "session", "board", "system"]
"""Valid log component names."""
```

### Backward Compatibility

**Legacy `quinn.log` behavior:**
- Remains unchanged for users who tail it
- Same plain text format
- Same rotation policy (10MB, 5 backups)
- Can be disabled with `legacy_logging=False` flag

**Migration path:**
- Old code continues to work (uses plain text)
- New code uses enhanced logging (JSON + plain text)
- Board UI migrates to use component loggers
- No breaking changes

---

## Testing Strategy

### Unit Tests (to write FIRST per TDD)

**Test file:** `cli/tests/test_enhanced_logging.py`

```python
def test_component_log_directory_creation():
    """Test that component directories are created."""

def test_json_log_format():
    """Test JSON log entry structure."""

def test_daily_log_rotation():
    """Test new file created each day."""

def test_log_retention_cleanup():
    """Test old logs deleted after retention period."""

def test_dual_output_plain_and_json():
    """Test logs written to both formats."""

def test_component_specific_files():
    """Test worker logs go to workers/, etc."""
```

**Test file:** `cli/tests/test_log_reader.py`

```python
def test_list_components():
    """Test listing components with logs."""

def test_list_dates():
    """Test listing dates for component."""

def test_read_logs_with_filters():
    """Test filtering by level, date, component."""

def test_search_logs_by_keyword():
    """Test full-text search."""

def test_tail_logs():
    """Test getting most recent entries."""

def test_large_file_performance():
    """Test reading 10,000+ entries efficiently."""
```

### Integration Tests

```python
def test_end_to_end_logging_flow():
    """Test log → write → read → display pipeline."""

def test_multiple_components_simultaneously():
    """Test concurrent logging from multiple components."""
```

---

## Consequences

### Positive
- ✅ Efficient UI querying (structured JSON)
- ✅ Easy per-component filtering
- ✅ Backward compatible (legacy plain text remains)
- ✅ Scalable to many workers
- ✅ Automatic cleanup (retention policy)
- ✅ Better developer experience (structured context)

### Negative
- ⚠️ Increased disk usage (~810 MB vs ~60 MB)
- ⚠️ Dual logging adds small CPU overhead (negligible)
- ⚠️ Migration work for board UI components

### Neutral
- Existing code continues to work unchanged
- New features require using enhanced logging

---

## Alternatives Considered

### Single Centralized Log Database (SQLite)
**Rejected because:**
- Adds complexity (schema management, migrations)
- Overkill for local file-based logging
- File corruption risk
- Harder to debug than plain files

### Send Logs to Remote Service (Datadog, CloudWatch)
**Rejected because:**
- QuinnAI is local-first
- Privacy concerns (logs contain org data)
- Requires network connectivity
- Adds external dependencies

### Keep Current System, Parse in UI
**Rejected because:**
- Poor performance (regex parsing in UI)
- Hard to filter efficiently
- No structured querying
- Defeats purpose of good logging

---

## Implementation Order (TDD)

1. **Write FAILING tests** (test_enhanced_logging.py, test_log_reader.py)
2. **Watch tests FAIL** (run pytest, verify failures)
3. **Implement** (extend logging.py, create log_reader.py, log_formatters.py)
4. **Watch tests PASS** (run pytest, verify all green)

---

## Related Documents

- **Audit:** `shared/docs/logging-audit.md` - Current state analysis
- **Epic:** `quinnai-clck` - Add Logs Tab to qn-board UI
- **Next Task:** `quinnai-7ndf` - TDD: Implement centralized logging module

---

## Approval

This ADR is **proposed** and awaiting review.

**Review by:** User
**Implementation by:** Claude Code
**Target completion:** Sprint 2

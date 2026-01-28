# QuinnAI Logging Infrastructure Audit

**Date:** 2026-01-28
**Auditor:** Claude Code
**Task:** quinnai-tcu3 - Investigate existing logging infrastructure

---

## Executive Summary

QuinnAI **already has a comprehensive centralized logging system** in place at `cli/core/logging.py`. The system features:
- ✅ Structured logging with log levels (DEBUG, INFO, WARNING, ERROR)
- ✅ File output to `org_path/live/logs/quinn.log`
- ✅ Automatic log rotation (10MB max, 5 backups)
- ✅ Console output controlled by verbosity flags
- ✅ Helper functions for common log events
- ✅ Comprehensive test coverage (cli/tests/test_logging.py)

**Conclusion:** The infrastructure is solid. The main gaps are:
1. **No UI to view logs** (the whole point of this epic)
2. **Board UI doesn't use centralized logging** (uses Python logging directly)
3. **No per-component log segregation** (all logs go to single quinn.log)
4. **No structured JSON format** (uses plain text format)

---

## 1. Current Logging Infrastructure

### Location
- **Primary Module:** `cli/core/logging.py`
- **Initialization:** `cli/commands/main.py` (qn CLI entry point)
- **Tests:** `cli/tests/test_logging.py`

### Log File Locations
```
org_path/
└── live/
    └── logs/
        ├── quinn.log           # Main log file (current)
        ├── quinn.log.1         # Rotated backup 1
        ├── quinn.log.2         # Rotated backup 2
        ├── quinn.log.3         # Rotated backup 3
        ├── quinn.log.4         # Rotated backup 4
        └── quinn.log.5         # Rotated backup 5

.beads/
└── daemon.log                  # Beads daemon logs (Go, different format)
```

### Log Format

**Current format (plain text):**
```
2026-01-22 15:04:07 [INFO] quinn.cli.core.worker: Worker lifecycle: Alice (wrkr-1986b531) pending -> onboarding
```

**Format string:**
```python
DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
```

### Log Rotation
- **Strategy:** Size-based rotation using `RotatingFileHandler`
- **Max file size:** 10 MB (`MAX_LOG_SIZE_BYTES`)
- **Backup count:** 5 files (`BACKUP_COUNT`)
- **Total max storage:** ~60 MB per org (10MB × 6 files)

### Log Levels
- **DEBUG:** Budget checks, detailed session events
- **INFO:** Lifecycle changes, session spawn/stop, budget spend
- **WARNING:** Configuration issues, deprecations
- **ERROR:** Failures, exceptions

---

## 2. Components Currently Logging

### ✅ Using Centralized Logging (`cli/core/logging.get_logger`)

| Component | File | Log Events |
|-----------|------|------------|
| Budget System | `cli/core/budget.py` | Budget checks, spend tracking |
| Org Lifecycle | `cli/core/org.py` | Org state changes |
| Worker Lifecycle | `cli/core/worker.py` | Lifecycle transitions, session events |
| Sessions | `cli/core/sessions/*.py` | Session spawn/stop |

**Usage pattern:**
```python
from cli.core.logging import get_logger
_logger = get_logger(__name__)
_logger.info("Worker lifecycle: %s -> %s", old, new)
```

### ⚠️ Using Python Logging Directly (Not Centralized)

| Component | File | Issue |
|-----------|------|-------|
| Board UI Views | `terminal-app/src/board_ui/views/okrs.py` | Uses `import logging` directly |
| Board UI Views | `terminal-app/src/board_ui/views/team.py` | Uses `import logging` directly |
| Board Services | `terminal-app/src/board_ui/services/org_discovery.py` | Uses `import logging` directly |
| Board Services | `terminal-app/src/board_ui/services/org_connection.py` | Uses `import logging` directly |

**Problem:** These may not respect our log configuration or output to the correct file.

### ❌ Not Logging (Gaps)

| Component | Missing Logs |
|-----------|--------------|
| Beads operations | No logs for issue creation, updates, searches |
| Message system | No logs for message send/receive |
| Storage operations | No logs for file operations |
| HTTP/API calls | No logs for external requests (if any) |

---

## 3. Test Coverage

### Existing Tests (`cli/tests/test_logging.py`)

**Coverage is excellent:**
- ✅ Logger creation and caching
- ✅ Configuration with different verbosity levels
- ✅ File handler setup and rotation
- ✅ Console handler setup
- ✅ Multiple logger instances
- ✅ Structured logging helper functions
- ✅ Log file path retrieval
- ✅ Error handling for invalid paths

**Test count:** 18 tests, all passing

---

## 4. Current Limitations

### 1. Single Log File
**Problem:** All components log to `quinn.log`, making it hard to filter by component.

**Impact:**
- Hard to find worker-specific logs
- Can't easily separate CLI vs session vs board events
- Log rotation affects all components equally

**Recommendation:** Consider component-specific log files:
```
logs/
├── cli.log          # CLI commands
├── workers/         # Per-worker logs
│   ├── ceo.log
│   └── engineer-123.log
├── sessions.log     # Session lifecycle
└── board.log        # Board UI events
```

### 2. Plain Text Format
**Problem:** Current format is human-readable but not machine-parsable.

**Current:**
```
2026-01-22 15:04:07 [INFO] quinn.cli.core.worker: Worker lifecycle: Alice (wrkr-1986b531) pending -> onboarding
```

**Better (structured JSON):**
```json
{"timestamp":"2026-01-22T15:04:07Z","level":"INFO","component":"worker","event":"lifecycle_change","worker_id":"wrkr-1986b531","worker_name":"Alice","old_status":"pending","new_status":"onboarding"}
```

**Benefits of JSON:**
- Easy to parse programmatically
- Structured search (e.g., all events for worker X)
- Machine learning on logs
- Export to log aggregation tools

### 3. No Board UI Integration
**Problem:** The board UI doesn't use the centralized logging system consistently.

**Solution needed:** Make board UI use `cli.core.logging.get_logger()`

### 4. No UI to View Logs
**Problem:** Logs exist but there's no way to view them without leaving the terminal.

**Solution:** This is the whole point of the epic - build the Logs tab!

---

## 5. Beads Daemon Logs

**Separate system:** The beads daemon (Go-based) has its own logging to `.beads/daemon.log`.

**Format:** Structured Go logging:
```
time=2026-01-21T13:47:02.210-08:00 level=INFO msg="Daemon started"
```

**Note:** This is separate from QuinnAI's Python logs. We may want to aggregate both in the UI.

---

## 6. Recommendations

### Keep (Already Good)
1. ✅ Centralized `cli/core/logging.py` module
2. ✅ Size-based rotation with backups
3. ✅ Helper functions for structured events
4. ✅ Comprehensive test coverage
5. ✅ Console vs file verbosity control

### Fix (Migration needed)
1. ⚠️ Migrate board UI to use centralized logging
2. ⚠️ Add logging to missing components (beads, messaging, storage)

### Enhance (New features for Logs tab)
1. 📝 Add JSON structured format option
2. 📝 Add per-component log segregation
3. 📝 Build log reader API (quinnai-fzyq)
4. 📝 Build Logs tab UI (quinnai-lalj)

---

## 7. Next Steps

Based on this audit, the implementation plan should be:

### Phase 1: Enhance Current System (quinnai-7ndf)
- Add JSON formatter option
- Add per-component log files
- Keep backward compatibility

### Phase 2: Build Log Reader API (quinnai-fzyq)
- Parse both plain text and JSON logs
- Filter by component, level, time range
- Search by keyword
- Tail logs live

### Phase 3: Build UI (quinnai-lalj)
- Display logs in board
- Filter controls
- Search functionality
- Auto-refresh

### Phase 4: Migration (quinnai-2rvu)
- Migrate board UI to centralized logging
- Add logging to missing components
- Remove direct `import logging` usage

---

## 8. Files Involved

### Core Logging
- `cli/core/logging.py` - Main module (328 lines)
- `cli/core/constants.py` - Constants like LIVE_DIR
- `cli/tests/test_logging.py` - Test suite

### Components Using Logging
- `cli/core/budget.py`
- `cli/core/org.py`
- `cli/core/worker.py`
- `cli/core/sessions/*.py`

### Components Needing Migration
- `terminal-app/src/board_ui/views/okrs.py`
- `terminal-app/src/board_ui/views/team.py`
- `terminal-app/src/board_ui/services/org_discovery.py`
- `terminal-app/src/board_ui/services/org_connection.py`

### New Files to Create
- `cli/core/log_reader.py` - Log retrieval API
- `terminal-app/src/board_ui/views/logs.py` - Logs tab UI
- `shared/logging.py` - Shared logging utilities (if needed)

---

## Appendix: Example Log Entries

### Worker Lifecycle
```
2026-01-22 15:04:07 [INFO] quinn.cli.core.worker: Worker lifecycle: Alice (wrkr-1986b531) onboarding -> active
```

### Budget Operations
```
2026-01-22 15:04:07 [DEBUG] quinn.cli.core.budget: Budget check approved: worker=wrkr-1986b531, required=$0.0675, available=$1000.0000
2026-01-22 15:04:07 [INFO] quinn.cli.core.budget: Budget spend: worker=wrkr-1986b531, amount=$0.0675, provider=claude_code, model=premium-tier
```

### Session Events
```
2026-01-22 15:04:07 [INFO] quinn.cli.core.worker: Session spawned: worker=Alice (wrkr-1986b531), provider=claude_code, session_id=wrkr-1986b531:67de427bf674
```

### Org State Changes
```
2026-01-22 15:04:01 [INFO] quinn.cli.core.org: Org state change: uninitialized -> initialized
2026-01-22 15:04:07 [INFO] quinn.cli.core.org: Org state change: initialized -> running
```

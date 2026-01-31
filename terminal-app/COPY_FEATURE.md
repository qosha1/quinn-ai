# Board UI Copy/Export Feature

## Overview
The Board UI now supports copying view content to the clipboard or exporting to a file using the 'c' keyboard shortcut.

## Usage

1. **Navigate to any view** (Dashboard, Messages, Logs, Team, OKRs, Settings)
2. **Press 'c' key**
3. **Content is copied** to clipboard (if available) or saved to file

## Implementation Details

### Keyboard Binding
- **Key:** `c`
- **Action:** `copy_current_view`
- **Shown in footer:** Yes

### Copy Strategy
1. **Primary:** Try to copy to system clipboard using `pbcopy` (macOS) or `xclip` (Linux)
2. **Fallback:** If clipboard unavailable, write to file in `<org-path>/exports/` directory

### Export Format
All views export to plain text with:
- Clear section headers (====== separators)
- Structured data layout
- Preserved indentation
- Human-readable format

### Supported Views

#### Dashboard
- Organization name and status
- CEO information (name, role, session state)
- Budget metrics (today, week, total)
- Health status (score, workers, issues)
- Recent activity

#### Messages
- Current channel name
- Unread message count
- All messages with:
  - Sender name
  - Timestamp
  - Priority level
  - Full message content

#### Logs
- Current filter settings (component, level, search)
- Page number
- All visible log entries with timestamps

#### Team
- Current filter (All/Active/Idle)
- Worker count
- Each worker's:
  - Name, ID, role, team
  - Manager
  - Status and session state
  - Current task

#### OKRs
- Total OKR count
- Hierarchical OKR structure
- Each OKR shows:
  - Title and owner
  - Progress (completed/total KRs)
  - Key results with current/target values

#### Settings
- Default provider
- Available providers with:
  - Status (enabled/disabled)
  - Aliases
  - Capabilities

## File Export Location

When clipboard is unavailable:
- **Org-connected:** `<org-path>/exports/board_<view>_<timestamp>.txt`
- **No org:** `<temp-dir>/quinnai_exports/board_<view>_<timestamp>.txt`

Filename format: `board_<view>_YYYYMMDD_HHMMSS.txt`

Example: `board_dashboard_20260131_143022.txt`

## Testing

Run the test suite:
```bash
python -m pytest terminal-app/tests/test_copy_export.py -v
```

All 11 tests pass:
- Keyboard binding exists
- Each view exports text correctly
- Clipboard copy works
- File fallback works
- Proper handling when not connected to org
- Exported text preserves structure

## User Benefits

1. **Share error messages** - Copy logs/errors to paste in bug reports
2. **Report health status** - Export dashboard metrics for team reviews
3. **Document worker state** - Copy team view for status updates
4. **Archive messages** - Save important escalation threads
5. **Track OKR progress** - Export objectives for external reporting

## Future Enhancements

Potential improvements (not implemented):
- Copy selection (specific rows/sections)
- Export to different formats (JSON, CSV)
- Email export directly from Board
- Automatic periodic snapshots

# Logs Tab User Guide

## Overview

The Logs tab displays system logs from all QuinnAI components in a searchable, filterable interface.

## Access

**Keyboard**: Press `L` from any tab

**Navigation**: Click "Logs" in the tab bar

## Interface

```
[Component: All] [Level: All] [Search: ____] [Auto-refresh: ON]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2026-01-28 10:15:23 [INFO ] worker    : Worker started
2026-01-28 10:15:24 [DEBUG] session   : Spawning session
2026-01-28 10:15:25 [ERROR] cli       : Command failed
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[◀ Prev] Page 1 [Next ▶]
```

## Filtering

**Component Filter**
- All Components (default)
- CLI
- Workers
- Sessions
- Board
- System

**Level Filter**
- All Levels (default)
- DEBUG
- INFO
- WARNING
- ERROR
- CRITICAL

Filters apply immediately on selection.

## Search

Enter keywords in the search box. Searches across:
- Log messages
- Component names
- Context fields

Search is case-insensitive. Press Enter to execute.

## Pagination

Default page size: 50 entries

**Navigate**:
- Next page: Click "Next ▶" or use pagination controls
- Previous page: Click "◀ Prev"

Page number displays current position.

## Auto-refresh

Toggle ON: Logs refresh every 2 seconds
Toggle OFF: Manual refresh only (press `R`)

## Log Levels

Logs display with color-coded severity:
- ERROR: Red text
- WARNING: Yellow text
- INFO: Normal text
- DEBUG: Muted text

## Troubleshooting

**No logs appear**:
1. Verify org is running
2. Check org_path/live/logs/ directory exists
3. Generate activity (run commands, spawn workers)

**Slow performance**:
1. Reduce date range with filters
2. Use specific component filter
3. Disable auto-refresh when not needed

**Empty search results**:
- Verify search term spelling
- Try broader search terms
- Check component filter isn't too restrictive

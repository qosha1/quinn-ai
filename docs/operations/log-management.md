# Log Management Operations Guide

## Directory Structure

```
org_path/
└── live/
    └── logs/
        ├── quinn.log              # Legacy aggregated (10MB, 5 backups)
        ├── quinn.log.1-5          # Rotated backups
        ├── cli/
        │   ├── 2026-01-28.json
        │   └── 2026-01-27.json
        ├── workers/
        │   ├── 2026-01-28.json
        │   └── 2026-01-27.json
        ├── sessions/
        │   ├── 2026-01-28.json
        │   └── 2026-01-27.json
        ├── board/
        │   ├── 2026-01-28.json
        │   └── 2026-01-27.json
        └── system/
            ├── 2026-01-28.json
            └── 2026-01-27.json
```

## Log Files

**JSON Logs** (per-component):
- Format: JSONL (JSON Lines)
- Naming: `YYYY-MM-DD.json`
- Rotation: Daily (new file each day)
- Size: Varies (1-5 MB per day typical)

**Legacy Log** (aggregated):
- Format: Plain text
- File: `quinn.log`
- Rotation: Size-based (10 MB max)
- Backups: 5 files retained

## Rotation Policies

**Daily Rotation** (JSON logs):
- New file created at midnight
- Old files retained for 30 days
- Automatic cleanup on startup
- No size limit per file

**Size-based Rotation** (legacy log):
- Rotates at 10 MB
- Keeps 5 backups (60 MB total)
- Oldest backup deleted on rotation

## Retention

**Default**: 30 days for JSON logs

**Configure**:
```python
# In cli/core/constants.py
LOG_RETENTION_DAYS = 30  # Change to desired days
```

**Manual Cleanup**:
```bash
# Delete logs older than 30 days
find org_path/live/logs/*/  -name "*.json" -mtime +30 -delete
```

## Disk Space

**Typical Usage**:
- Per component: 1-5 MB per day
- 5 components × 5 MB × 30 days = 750 MB
- Legacy log: 60 MB
- Total: ~810 MB per org

**Monitor**:
```bash
# Check total log size
du -sh org_path/live/logs/

# Check per component
du -sh org_path/live/logs/*/
```

**Reduce Usage**:
1. Lower retention: Set `LOG_RETENTION_DAYS` to 7 or 14
2. Disable legacy log: Set `legacy_logging=False`
3. Reduce log levels: Use INFO instead of DEBUG

## Reading Logs

**JSON Logs**:
```bash
# View today's worker logs
cat org_path/live/logs/workers/2026-01-28.json | jq .

# Filter ERROR level
cat org_path/live/logs/workers/*.json | jq 'select(.level=="ERROR")'

# Search for keyword
grep -h "timeout" org_path/live/logs/workers/*.json | jq .
```

**Legacy Log**:
```bash
# Tail live
tail -f org_path/live/logs/quinn.log

# Search
grep "ERROR" org_path/live/logs/quinn.log

# Last 100 lines
tail -100 org_path/live/logs/quinn.log
```

## Backup

**Backup logs**:
```bash
# Archive last 7 days
tar -czf logs-$(date +%Y%m%d).tar.gz \
  $(find org_path/live/logs/ -name "*.json" -mtime -7)

# Archive all logs
tar -czf logs-full-$(date +%Y%m%d).tar.gz \
  org_path/live/logs/
```

**Restore**:
```bash
tar -xzf logs-20260128.tar.gz -C org_path/live/
```

## Troubleshooting

**Logs not appearing**:
1. Check logging configured: `grep configure_enhanced_logging cli/`
2. Verify directory exists: `ls org_path/live/logs/`
3. Check permissions: `ls -la org_path/live/logs/`
4. Review stderr for errors

**Large log files**:
1. Check for tight loops: `grep -c "message" log.json`
2. Reduce log level from DEBUG to INFO
3. Lower retention period
4. Add rate limiting to log calls

**Rotation not working**:
1. Verify cleanup runs: Check startup logs
2. Manual cleanup: Delete old `*.json` files
3. Check `LOG_RETENTION_DAYS` constant

**Disk space full**:
1. Immediate: `find org_path/live/logs/ -name "*.json" -mtime +7 -delete`
2. Long-term: Reduce `LOG_RETENTION_DAYS`
3. Archive old logs: Use tar backup method above

## Performance

**Log write performance**:
- JSON logs: Append-only (fast)
- No impact on org operations
- Async writes (non-blocking)

**Log read performance**:
- 100 entries: <100ms
- 10,000 entries: <1s
- Streaming reads (memory-efficient)

**Optimize reads**:
1. Use specific component filter
2. Limit date range
3. Use pagination (limit/offset)
4. Disable auto-refresh when not needed

## Security

**Log permissions**:
```bash
# Verify owner
ls -la org_path/live/logs/

# Should be: user:group, mode 755 for dirs, 644 for files
```

**Sensitive data**:
- Logs may contain worker IDs, session IDs
- Do not share logs publicly
- Sanitize before sharing (redact IDs)

**Log rotation security**:
- Old logs automatically deleted
- No sensitive data retained beyond retention period

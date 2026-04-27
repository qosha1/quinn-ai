"""Cross-cutting numeric constants for the board UI.

Mirrors cli/core/constants.py — values that appear in more than one place
or that need to be tunable without grep-and-replace live here.

Per-adapter probe timeouts (terminals/*, clipboard_exporter pbcopy/xclip,
internal sqlite connect timeouts) intentionally stay local: those are tied
to the specific tool being probed, not a board-wide concern.
"""

# ----- polling intervals (seconds) -----

# WAL-page-count polling cadence on the active org connection. Drives
# reactive view refreshes when the board detects a database write.
WAL_POLL_INTERVAL_SECONDS = 0.3

# Per-view auto-refresh tick used by Dashboard and Team while a view is
# mounted. Independent of WAL polling and intentionally slower.
VIEW_REFRESH_INTERVAL_SECONDS = 2

# Recent-activity widget tail-rescan interval. Activity is jsonl on disk,
# not in the db, so it isn't covered by WAL polling.
ACTIVITY_REFRESH_INTERVAL_SECONDS = 30

# ----- DB-locked retry/backoff (when opening a QuinnAIOrgConnection) -----

# Total connect attempts including the first. With base 0.5 and 3 retries,
# total worst-case sleep is 0.5 + 1.0 = 1.5s before failing.
DB_LOCKED_MAX_RETRIES = 3

# Backoff base for `delay = base * (2 ** attempt)`. attempt 0 → 0.5s,
# attempt 1 → 1.0s, attempt 2 → 2.0s.
DB_LOCKED_BACKOFF_BASE_SECONDS = 0.5

# ----- qn CLI subprocess timeouts -----

# `qn --help` smoke probe used by QnCliClient.available().
QN_HELP_TIMEOUT_SECONDS = 5

# Default subprocess timeout for plain `qn ...` runs without a domain-
# specific override (e.g. provider-list, fire). Long-running CLI ops
# (start/stop/restart) override this on the call site.
QN_DEFAULT_TIMEOUT_SECONDS = 30

# `qn org restart` timeout. Stop + start can take a while.
QN_RESTART_TIMEOUT_SECONDS = 60

/**
 * Tests for timestamp formatting utilities.
 *
 * formatRelativeTime tests: should pass (function exists).
 * formatAbsoluteTimestamp tests: INTENTIONALLY FAILING — function does not
 * yet exist in @/lib/transforms.
 */

import { describe, it, expect } from "vitest";
// formatAbsoluteTimestamp does not exist yet — this import will fail at
// runtime, causing these tests to error/fail as intended.
import { formatRelativeTime, formatAbsoluteTimestamp } from "@/lib/transforms";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isoSecondsAgo(seconds: number): string {
  return new Date(Date.now() - seconds * 1000).toISOString();
}

function isoHoursAgo(hours: number): string {
  return isoSecondsAgo(hours * 3600);
}

function isoYesterday(hour: number, minute: number): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  d.setHours(hour, minute, 0, 0);
  return d.toISOString();
}

function isoToday(hour: number, minute: number): string {
  const d = new Date();
  d.setHours(hour, minute, 0, 0);
  return d.toISOString();
}

function isoOlderDate(year: number, month: number, day: number, hour: number, minute: number): string {
  // month is 1-based for readability
  const d = new Date(year, month - 1, day, hour, minute, 0, 0);
  return d.toISOString();
}

// ---------------------------------------------------------------------------
// formatRelativeTime (function exists — these should pass)
// ---------------------------------------------------------------------------

describe("formatRelativeTime", () => {
  it("returns 'just now' for < 60 seconds ago", () => {
    expect(formatRelativeTime(isoSecondsAgo(30))).toBe("just now");
  });

  it("returns '4h ago' for 4 hours ago", () => {
    expect(formatRelativeTime(isoHoursAgo(4))).toBe("4h ago");
  });
});

// ---------------------------------------------------------------------------
// formatAbsoluteTimestamp (function does NOT exist — these will fail)
// ---------------------------------------------------------------------------

describe("formatAbsoluteTimestamp", () => {
  it("returns 'Yesterday 14:32' for yesterday at 14:32", () => {
    const iso = isoYesterday(14, 32);
    expect(formatAbsoluteTimestamp(iso)).toBe("Yesterday 14:32");
  });

  it("returns 'Apr 28, 14:32' for an older date", () => {
    // Use a fixed past date that is guaranteed not to be today or yesterday
    const iso = isoOlderDate(2026, 4, 28, 14, 32);
    expect(formatAbsoluteTimestamp(iso)).toBe("Apr 28, 14:32");
  });

  it("returns 'Today 09:15' for today at 09:15", () => {
    const iso = isoToday(9, 15);
    expect(formatAbsoluteTimestamp(iso)).toBe("Today 09:15");
  });
});

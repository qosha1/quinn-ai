import { describe, it, expect, beforeAll, afterAll } from "vitest";
import Database from "better-sqlite3";
import fs from "fs";
import path from "path";
import os from "os";

let tmpDir: string;
let dbPath: string;

function createFixtureDb(dbPath: string): Database.Database {
  const db = new Database(dbPath);
  db.exec(`
    CREATE TABLE org_state (
      id TEXT PRIMARY KEY DEFAULT 'default',
      name TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'initialized',
      ceo_worker_id TEXT,
      started_at TEXT,
      stopped_at TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE workers (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'worker',
      team_id TEXT,
      manager_id TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      skills TEXT DEFAULT '{}',
      cost REAL DEFAULT 100,
      hiring_authority_scope TEXT DEFAULT '[]',
      delegated_budget REAL DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE channels (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      type TEXT DEFAULT 'topic',
      team_id TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE messages (
      id TEXT PRIMARY KEY,
      channel_id TEXT NOT NULL,
      thread_id TEXT,
      parent_id TEXT,
      from_worker_id TEXT NOT NULL,
      content TEXT NOT NULL,
      priority INTEGER DEFAULT 2,
      time_sensitivity TEXT DEFAULT 'whenever',
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE notification_beads (
      id TEXT PRIMARY KEY,
      worker_id TEXT NOT NULL,
      message_id TEXT NOT NULL,
      channel_id TEXT,
      status TEXT DEFAULT 'pending',
      priority INTEGER DEFAULT 2,
      created_at TEXT DEFAULT (datetime('now')),
      read_at TEXT,
      actioned_at TEXT,
      closed_at TEXT,
      expires_at TEXT
    );

    INSERT INTO org_state VALUES ('default', 'test-org', 'running', 'worker-ceo-1', datetime('now'), NULL, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-ceo-1', 'Alice', 'CEO', NULL, NULL, 'active', '{}', 100, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO channels VALUES ('chan-alpha', 'alpha', 'topic', NULL, datetime('now'));
    INSERT INTO channels VALUES ('chan-beta', 'beta', 'topic', NULL, datetime('now'));

    INSERT INTO messages VALUES ('msg-a1', 'chan-alpha', NULL, NULL, 'worker-ceo-1', 'Alpha message 1', 2, 'whenever', datetime('now', '-2 minutes'));
    INSERT INTO messages VALUES ('msg-a2', 'chan-alpha', NULL, NULL, 'worker-ceo-1', 'Alpha message 2', 2, 'whenever', datetime('now', '-1 minutes'));
    INSERT INTO messages VALUES ('msg-b1', 'chan-beta', NULL, NULL, 'worker-ceo-1', 'Beta message 1', 2, 'whenever', datetime('now'));

    INSERT INTO notification_beads VALUES ('nb-a1', 'worker-ceo-1', 'msg-a1', 'chan-alpha', 'pending', 2, datetime('now'), NULL, NULL, NULL, NULL);
    INSERT INTO notification_beads VALUES ('nb-a2', 'worker-ceo-1', 'msg-a2', 'chan-alpha', 'pending', 2, datetime('now'), NULL, NULL, NULL, NULL);
    INSERT INTO notification_beads VALUES ('nb-b1', 'worker-ceo-1', 'msg-b1', 'chan-beta', 'pending', 2, datetime('now'), NULL, NULL, NULL, NULL);
  `);
  return db;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "quinn-mark-read-test-"));
  dbPath = path.join(tmpDir, "quinn.db");
  createFixtureDb(dbPath);
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("markChannelRead", () => {
  it("markChannelRead marks all messages in channel as read", async () => {
    const { markChannelRead } = await import("@/lib/db");
    markChannelRead(dbPath, "alpha");
    // No thrown error means it ran; the next test verifies the actual state
  });

  it("getMessages returns is_read=true for all messages after markChannelRead", async () => {
    const { markChannelRead, getMessages } = await import("@/lib/db");
    markChannelRead(dbPath, "alpha");
    const msgs = getMessages(dbPath, "alpha");
    expect(msgs.length).toBeGreaterThan(0);
    expect(msgs.every((m) => m.is_read === true)).toBe(true);
  });

  it("markChannelRead is idempotent", async () => {
    const { markChannelRead, getMessages } = await import("@/lib/db");
    markChannelRead(dbPath, "alpha");
    markChannelRead(dbPath, "alpha");
    const msgs = getMessages(dbPath, "alpha");
    expect(msgs.every((m) => m.is_read === true)).toBe(true);
  });
});

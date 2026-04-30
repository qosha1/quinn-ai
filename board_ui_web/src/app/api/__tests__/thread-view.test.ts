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

    INSERT INTO org_state VALUES ('default', 'test-org', 'running', 'worker-ceo-1', datetime('now'), NULL, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-ceo-1', 'Alice', 'CEO', NULL, NULL, 'active', '{}', 100, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-eng-1', 'Bob', 'worker', NULL, 'worker-ceo-1', 'active', '{}', 80, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO channels VALUES ('chan-general', 'general', 'topic', NULL, datetime('now'));

    -- Root message (thread_id = NULL, will serve as thread root)
    INSERT INTO messages VALUES ('msg-root', 'chan-general', NULL, NULL, 'worker-ceo-1', 'Root message', 2, 'whenever', datetime('now', '-10 minutes'));
    -- Two replies in the same thread
    INSERT INTO messages VALUES ('msg-reply-1', 'chan-general', 'msg-root', 'msg-root', 'worker-eng-1', 'First reply', 2, 'whenever', datetime('now', '-5 minutes'));
    INSERT INTO messages VALUES ('msg-reply-2', 'chan-general', 'msg-root', 'msg-reply-1', 'worker-ceo-1', 'Second reply', 2, 'whenever', datetime('now'));
    -- A message in a different thread (should NOT appear in results)
    INSERT INTO messages VALUES ('msg-other', 'chan-general', 'msg-other-root', 'msg-other-root', 'worker-eng-1', 'Different thread', 2, 'whenever', datetime('now'));
  `);
  return db;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "quinn-thread-view-test-"));
  dbPath = path.join(tmpDir, "quinn.db");
  createFixtureDb(dbPath);
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("getThreadMessages", () => {
  it("getThreadMessages returns all messages with matching thread_id", async () => {
    const { getThreadMessages } = await import("@/lib/db");
    const msgs = getThreadMessages(dbPath, "msg-root");
    // Both replies share thread_id = 'msg-root'
    expect(msgs.length).toBe(2);
    expect(msgs.every((m) => m.thread_id === "msg-root")).toBe(true);
  });

  it("getThreadMessages returns empty array for unknown thread_id", async () => {
    const { getThreadMessages } = await import("@/lib/db");
    const msgs = getThreadMessages(dbPath, "nonexistent-thread-id");
    expect(Array.isArray(msgs)).toBe(true);
    expect(msgs.length).toBe(0);
  });

  it("thread messages are sorted oldest first", async () => {
    const { getThreadMessages } = await import("@/lib/db");
    const msgs = getThreadMessages(dbPath, "msg-root");
    expect(msgs.length).toBeGreaterThan(1);
    for (let i = 1; i < msgs.length; i++) {
      expect(new Date(msgs[i - 1].created_at).getTime()).toBeLessThanOrEqual(
        new Date(msgs[i].created_at).getTime()
      );
    }
  });
});

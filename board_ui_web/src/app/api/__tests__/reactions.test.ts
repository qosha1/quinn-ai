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

    CREATE TABLE message_reactions (
      message_id TEXT NOT NULL,
      worker_id TEXT NOT NULL,
      emoji TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now')),
      PRIMARY KEY (message_id, worker_id, emoji)
    );

    INSERT INTO org_state VALUES ('default', 'test-org', 'running', 'worker-ceo-1', datetime('now'), NULL, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-ceo-1', 'Alice', 'CEO', NULL, NULL, 'active', '{}', 100, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-eng-1', 'Bob', 'worker', NULL, 'worker-ceo-1', 'active', '{}', 80, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO channels VALUES ('chan-board', 'board-channel', 'topic', NULL, datetime('now'));
    INSERT INTO messages VALUES ('msg-1', 'chan-board', NULL, NULL, 'worker-ceo-1', 'Status update: all tasks on track', 1, 'whenever', datetime('now'));
    INSERT INTO messages VALUES ('msg-2', 'chan-board', NULL, NULL, 'worker-eng-1', 'Blocked on API credentials', 0, 'immediate', datetime('now'));
  `);
  return db;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "quinn-reactions-test-"));
  dbPath = path.join(tmpDir, "quinn.db");
  createFixtureDb(dbPath);
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

// addReaction, removeReaction, getReactionCounts do not exist yet — tests must fail.

describe("addReaction", () => {
  it("addReaction inserts into message_reactions table", async () => {
    const { addReaction } = await import("@/lib/db");
    addReaction(dbPath, "msg-1", "worker-ceo-1", "👍");
    const db = new Database(dbPath);
    const row = db
      .prepare("SELECT * FROM message_reactions WHERE message_id=? AND worker_id=? AND emoji=?")
      .get("msg-1", "worker-ceo-1", "👍") as { message_id: string } | undefined;
    db.close();
    expect(row).toBeDefined();
  });

  it("addReaction is idempotent (same worker+emoji twice = no error)", async () => {
    const { addReaction } = await import("@/lib/db");
    expect(() => {
      addReaction(dbPath, "msg-1", "worker-ceo-1", "❤️");
      addReaction(dbPath, "msg-1", "worker-ceo-1", "❤️");
    }).not.toThrow();
  });
});

describe("removeReaction", () => {
  it("removeReaction deletes the row", async () => {
    const { addReaction, removeReaction } = await import("@/lib/db");
    addReaction(dbPath, "msg-2", "worker-eng-1", "🎉");
    removeReaction(dbPath, "msg-2", "worker-eng-1", "🎉");
    const db = new Database(dbPath);
    const row = db
      .prepare("SELECT * FROM message_reactions WHERE message_id=? AND worker_id=? AND emoji=?")
      .get("msg-2", "worker-eng-1", "🎉");
    db.close();
    expect(row).toBeUndefined();
  });
});

describe("getReactionCounts", () => {
  it("getReactionCounts returns {emoji: count} map for a message", async () => {
    const { addReaction, getReactionCounts } = await import("@/lib/db");
    addReaction(dbPath, "msg-1", "worker-eng-1", "👍");
    const counts = getReactionCounts(dbPath, "msg-1");
    expect(typeof counts).toBe("object");
    expect(counts["👍"]).toBeGreaterThanOrEqual(1);
  });
});

describe("getMessages includes reaction_counts", () => {
  it("getMessages includes reaction_counts in returned messages", async () => {
    const { getMessages } = await import("@/lib/db");
    const msgs = getMessages(dbPath, "board-channel");
    expect(msgs.length).toBeGreaterThan(0);
    // This should fail because getMessages doesn't return reaction_counts yet
    const msg = msgs.find((m: { id: string }) => m.id === "msg-1");
    expect(msg).toBeDefined();
    expect(msg).toHaveProperty("reaction_counts");
    expect(typeof (msg as { reaction_counts: unknown }).reaction_counts).toBe("object");
  });
});

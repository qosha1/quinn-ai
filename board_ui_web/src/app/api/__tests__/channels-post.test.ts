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
  `);
  return db;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "quinn-channels-post-test-"));
  dbPath = path.join(tmpDir, "quinn.db");
  createFixtureDb(dbPath);
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("postMessageToChannel", () => {
  it("creates message with correct channel_id and no parent_id", async () => {
    const { postMessageToChannel } = await import("@/lib/db");
    const msg = postMessageToChannel(dbPath, "chan-general", "worker-eng-1", "Hello channel");
    expect(msg.channel_id).toBe("chan-general");
    expect(msg.parent_id).toBeNull();
  });

  it("top-level message has null thread_id and null parent_id", async () => {
    const { postMessageToChannel } = await import("@/lib/db");
    const msg = postMessageToChannel(dbPath, "chan-general", "worker-eng-1", "Top-level post");
    expect(msg.thread_id).toBeNull();
    expect(msg.parent_id).toBeNull();
  });

  it("returns created message with id", async () => {
    const { postMessageToChannel } = await import("@/lib/db");
    const msg = postMessageToChannel(dbPath, "chan-general", "worker-ceo-1", "Status update");
    expect(typeof msg.id).toBe("string");
    expect(msg.id.length).toBeGreaterThan(0);
    expect(msg.content).toBe("Status update");
  });
});

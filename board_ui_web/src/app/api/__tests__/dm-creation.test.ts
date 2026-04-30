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

    CREATE TABLE channel_members (
      channel_id TEXT NOT NULL,
      worker_id TEXT NOT NULL,
      joined_at TEXT DEFAULT (datetime('now')),
      PRIMARY KEY (channel_id, worker_id)
    );

    INSERT INTO org_state VALUES ('default', 'test-org', 'running', 'worker-a', datetime('now'), NULL, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-a', 'Alice', 'CEO', NULL, NULL, 'active', '{}', 100, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-b', 'Bob', 'worker', NULL, 'worker-a', 'active', '{}', 80, '[]', 0, datetime('now'), datetime('now'));
  `);
  return db;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "quinn-dm-test-"));
  dbPath = path.join(tmpDir, "quinn.db");
  createFixtureDb(dbPath);
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

// createDirectChannel does not exist yet — all tests below must fail.
describe("createDirectChannel", () => {
  it("createDirectChannel creates channel with type=direct", async () => {
    const { createDirectChannel } = await import("@/lib/db");
    const channelId = createDirectChannel(dbPath, "worker-a", "worker-b");
    const db = new Database(dbPath);
    const row = db.prepare("SELECT * FROM channels WHERE id = ?").get(channelId) as { type: string } | undefined;
    db.close();
    expect(row).toBeDefined();
    expect(row?.type).toBe("direct");
  });

  it("createDirectChannel is idempotent — same channel returned on second call", async () => {
    const { createDirectChannel } = await import("@/lib/db");
    const first = createDirectChannel(dbPath, "worker-a", "worker-b");
    const second = createDirectChannel(dbPath, "worker-a", "worker-b");
    expect(first).toBe(second);
  });

  it("createDirectChannel subscribes both workers", async () => {
    const { createDirectChannel } = await import("@/lib/db");
    const channelId = createDirectChannel(dbPath, "worker-a", "worker-b");
    const db = new Database(dbPath);
    const members = db
      .prepare("SELECT worker_id FROM channel_members WHERE channel_id = ?")
      .all(channelId) as { worker_id: string }[];
    db.close();
    const ids = members.map((m) => m.worker_id);
    expect(ids).toContain("worker-a");
    expect(ids).toContain("worker-b");
  });

  it("createDirectChannel returns channel id", async () => {
    const { createDirectChannel } = await import("@/lib/db");
    const channelId = createDirectChannel(dbPath, "worker-a", "worker-b");
    expect(typeof channelId).toBe("string");
    expect(channelId.length).toBeGreaterThan(0);
  });
});

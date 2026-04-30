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
    INSERT INTO channels VALUES ('chan-eng', 'engineering', 'topic', NULL, datetime('now'));
    INSERT INTO channels VALUES ('chan-mkt', 'marketing', 'topic', NULL, datetime('now'));

    INSERT INTO messages VALUES ('msg-1', 'chan-eng', NULL, NULL, 'worker-ceo-1', 'Deploy the new authentication service', 2, 'whenever', datetime('now', '-3 minutes'));
    INSERT INTO messages VALUES ('msg-2', 'chan-eng', NULL, NULL, 'worker-ceo-1', 'Review pull request for authentication module', 2, 'whenever', datetime('now', '-2 minutes'));
    INSERT INTO messages VALUES ('msg-3', 'chan-mkt', NULL, NULL, 'worker-ceo-1', 'Launch the marketing campaign', 2, 'whenever', datetime('now', '-1 minutes'));
    INSERT INTO messages VALUES ('msg-4', 'chan-eng', NULL, NULL, 'worker-ceo-1', 'Fix database connection pool', 2, 'whenever', datetime('now'));
  `);
  return db;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "quinn-search-test-"));
  dbPath = path.join(tmpDir, "quinn.db");
  createFixtureDb(dbPath);
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("searchMessages", () => {
  it("searchMessages returns messages containing query term", async () => {
    const { searchMessages } = await import("@/lib/db");
    const results = searchMessages(dbPath, "authentication");
    expect(results.length).toBe(2);
    expect(results.every((m) => m.content.toLowerCase().includes("authentication"))).toBe(true);
  });

  it("searchMessages returns empty array for no match", async () => {
    const { searchMessages } = await import("@/lib/db");
    const results = searchMessages(dbPath, "zzznomatchzzz");
    expect(Array.isArray(results)).toBe(true);
    expect(results.length).toBe(0);
  });

  it("searchMessages results include channel_name and content", async () => {
    const { searchMessages } = await import("@/lib/db");
    const results = searchMessages(dbPath, "Deploy");
    expect(results.length).toBeGreaterThan(0);
    expect(typeof results[0].channel_name).toBe("string");
    expect(results[0].channel_name.length).toBeGreaterThan(0);
    expect(typeof results[0].content).toBe("string");
  });

  it("searchMessages with channelFilter only returns messages from that channel", async () => {
    const { searchMessages } = await import("@/lib/db");
    // 'authentication' matches both eng messages; filter to engineering only
    const results = searchMessages(dbPath, "authentication", "engineering");
    expect(results.length).toBe(2);
    expect(results.every((m) => m.channel_name === "engineering")).toBe(true);
  });
});

/**
 * Tests for channel subscription DB functions.
 *
 * INTENTIONALLY FAILING — subscribeToChannel, unsubscribeFromChannel, and
 * getChannelsWithSubscription do not yet exist in @/lib/db.
 */

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

    CREATE TABLE channel_subscriptions (
      channel_id TEXT NOT NULL,
      worker_id TEXT NOT NULL,
      subscribed_at TEXT DEFAULT (datetime('now')),
      PRIMARY KEY (channel_id, worker_id)
    );

    INSERT INTO org_state VALUES ('default', 'test-org', 'running', 'worker-ceo-1', datetime('now'), NULL, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-ceo-1', 'Alice', 'CEO', NULL, NULL, 'active', '{}', 100, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-eng-1', 'Bob', 'worker', NULL, 'worker-ceo-1', 'active', '{}', 80, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO channels VALUES ('chan-general', 'general', 'topic', NULL, datetime('now'));
    INSERT INTO channels VALUES ('chan-random', 'random', 'topic', NULL, datetime('now'));
  `);
  return db;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "quinn-channel-sub-test-"));
  dbPath = path.join(tmpDir, "quinn.db");
  createFixtureDb(dbPath);
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("subscribeToChannel", () => {
  it("adds row to channel_subscriptions", async () => {
    const { subscribeToChannel } = await import("@/lib/db");

    subscribeToChannel(dbPath, "chan-general", "worker-eng-1");

    const db = new Database(dbPath, { readonly: true });
    const row = db
      .prepare(
        "SELECT * FROM channel_subscriptions WHERE channel_id=? AND worker_id=?"
      )
      .get("chan-general", "worker-eng-1") as
      | { channel_id: string; worker_id: string }
      | undefined;
    db.close();

    expect(row).toBeDefined();
    expect(row?.channel_id).toBe("chan-general");
    expect(row?.worker_id).toBe("worker-eng-1");
  });

  it("subscribeToChannel is idempotent", async () => {
    const { subscribeToChannel } = await import("@/lib/db");

    // Call twice — must not throw or create duplicate rows
    subscribeToChannel(dbPath, "chan-general", "worker-ceo-1");
    subscribeToChannel(dbPath, "chan-general", "worker-ceo-1");

    const db = new Database(dbPath, { readonly: true });
    const rows = db
      .prepare(
        "SELECT * FROM channel_subscriptions WHERE channel_id=? AND worker_id=?"
      )
      .all("chan-general", "worker-ceo-1");
    db.close();

    expect(rows).toHaveLength(1);
  });
});

describe("unsubscribeFromChannel", () => {
  it("removes row from channel_subscriptions", async () => {
    const { subscribeToChannel, unsubscribeFromChannel } = await import(
      "@/lib/db"
    );

    subscribeToChannel(dbPath, "chan-random", "worker-eng-1");
    unsubscribeFromChannel(dbPath, "chan-random", "worker-eng-1");

    const db = new Database(dbPath, { readonly: true });
    const row = db
      .prepare(
        "SELECT * FROM channel_subscriptions WHERE channel_id=? AND worker_id=?"
      )
      .get("chan-random", "worker-eng-1");
    db.close();

    expect(row).toBeUndefined();
  });
});

describe("getChannelsWithSubscription", () => {
  it("returns subscribed boolean per channel", async () => {
    const { subscribeToChannel, getChannelsWithSubscription } = await import(
      "@/lib/db"
    );

    // Subscribe worker-ceo-1 to general only
    subscribeToChannel(dbPath, "chan-general", "worker-ceo-1");

    const channels = getChannelsWithSubscription(dbPath, "worker-ceo-1");

    expect(Array.isArray(channels)).toBe(true);
    expect(channels.length).toBeGreaterThanOrEqual(2);

    const general = channels.find((c: { id: string }) => c.id === "chan-general");
    const random = channels.find((c: { id: string }) => c.id === "chan-random");

    expect(general).toBeDefined();
    expect(general?.subscribed).toBe(true);

    expect(random).toBeDefined();
    expect(random?.subscribed).toBe(false);
  });
});

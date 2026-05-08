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

    CREATE TABLE teams (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      parent_team_id TEXT,
      lead_id TEXT,
      channel_id TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE team_members (
      team_id TEXT NOT NULL,
      worker_id TEXT NOT NULL,
      role TEXT DEFAULT 'member',
      joined_at TEXT DEFAULT (datetime('now')),
      PRIMARY KEY (team_id, worker_id)
    );

    CREATE TABLE worker_state (
      worker_id TEXT PRIMARY KEY,
      runtime_status TEXT DEFAULT 'stopped',
      current_task_id TEXT,
      pid INTEGER,
      started_at TEXT,
      last_activity TEXT,
      tasks_completed INTEGER DEFAULT 0,
      tasks_failed INTEGER DEFAULT 0,
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE sessions (
      id TEXT PRIMARY KEY,
      worker_id TEXT NOT NULL,
      provider TEXT NOT NULL,
      model TEXT,
      state TEXT DEFAULT 'stopped',
      tmux_session_name TEXT,
      pid INTEGER,
      started_at TEXT,
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

    CREATE TABLE okrs (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      description TEXT,
      owner_worker_id TEXT NOT NULL,
      parent_okr_id TEXT,
      status TEXT DEFAULT 'active',
      key_results TEXT DEFAULT '[]',
      due_date TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE budget_pools (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      total_credits REAL DEFAULT 0,
      period_start TEXT,
      period_end TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE budget_allocations (
      id TEXT PRIMARY KEY,
      worker_id TEXT,
      source_worker_id TEXT,
      pool_id TEXT,
      allocated_credits REAL DEFAULT 0,
      spent_credits REAL DEFAULT 0,
      reserved_credits REAL DEFAULT 0,
      period_start TEXT,
      period_end TEXT,
      can_delegate INTEGER DEFAULT 0,
      delegation_limit REAL DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE budget_transactions (
      id TEXT PRIMARY KEY,
      allocation_id TEXT,
      worker_id TEXT,
      type TEXT NOT NULL,
      amount REAL NOT NULL,
      provider TEXT,
      model TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE status_changes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      old_status TEXT,
      new_status TEXT NOT NULL,
      changed_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE budget_balances (
      allocation_id TEXT PRIMARY KEY,
      worker_id TEXT NOT NULL,
      allocated REAL NOT NULL,
      spent REAL NOT NULL,
      reserved REAL NOT NULL,
      available REAL NOT NULL,
      delegated REAL NOT NULL,
      period_start TEXT NOT NULL,
      period_end TEXT NOT NULL,
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    -- Seed data
    INSERT INTO org_state VALUES ('default', 'test-org', 'running', 'worker-ceo-1', datetime('now'), NULL, datetime('now'), datetime('now'));

    INSERT INTO teams VALUES ('team-1', 'Engineering', NULL, 'worker-ceo-1', 'chan-1', datetime('now'));
    INSERT INTO workers VALUES ('worker-ceo-1', 'Alice', 'CEO', 'team-1', NULL, 'active', '{}', 100, '[]', 0, datetime('now'), datetime('now'));
    INSERT INTO workers VALUES ('worker-eng-1', 'Bob', 'worker', 'team-1', 'worker-ceo-1', 'active', '{}', 80, '[]', 0, datetime('now'), datetime('now'));

    INSERT INTO worker_state VALUES ('worker-ceo-1', 'running', NULL, 12345, datetime('now'), datetime('now'), 5, 0, datetime('now'));
    INSERT INTO worker_state VALUES ('worker-eng-1', 'idle', NULL, NULL, NULL, NULL, 2, 0, datetime('now'));

    INSERT INTO sessions VALUES ('sess-1', 'worker-ceo-1', 'claude_code', 'claude-sonnet-4-5', 'running', 'quinn-ceo', 12345, datetime('now'), datetime('now'), datetime('now'));

    INSERT INTO channels VALUES ('chan-board', 'board-channel', 'topic', NULL, datetime('now'));
    INSERT INTO messages VALUES ('msg-1', 'chan-board', NULL, NULL, 'worker-ceo-1', 'Status update: all tasks on track', 1, 'whenever', datetime('now'));
    INSERT INTO messages VALUES ('msg-2', 'chan-board', NULL, NULL, 'worker-eng-1', 'Blocked on API credentials', 0, 'immediate', datetime('now'));

    INSERT INTO okrs VALUES ('okr-1', 'Q1 Revenue Goal', 'Reach $100k ARR', 'worker-ceo-1', NULL, 'active', '[{"title":"Outreach calls","current":5,"target":20}]', datetime('now', '+90 days'), datetime('now'), datetime('now'));
    INSERT INTO okrs VALUES ('okr-2', 'Ship v1.0', 'Launch product', 'worker-eng-1', 'okr-1', 'active', '[{"title":"Features complete","current":3,"target":5}]', datetime('now', '+30 days'), datetime('now'), datetime('now'));

    INSERT INTO budget_pools VALUES ('pool-1', 'main', 10000.0, datetime('now', '-30 days'), datetime('now', '+30 days'), datetime('now'), datetime('now'));
    INSERT INTO budget_allocations VALUES ('alloc-1', 'worker-ceo-1', NULL, 'pool-1', 5000.0, 0, 0, datetime('now', '-30 days'), datetime('now', '+30 days'), 1, 500, datetime('now'), datetime('now'));
    INSERT INTO budget_transactions VALUES ('tx-1', 'alloc-1', 'worker-ceo-1', 'spend', -150.0, 'claude_code', 'sonnet', datetime('now'));
    INSERT INTO budget_transactions VALUES ('tx-2', 'alloc-1', 'worker-ceo-1', 'spend', -50.0, 'claude_code', 'sonnet', datetime('now', '-5 days'));
  `);
  return db;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "quinn-board-test-"));
  dbPath = path.join(tmpDir, "quinn.db");
  createFixtureDb(dbPath);
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("getOrgInfo", () => {
  it("returns org name, status, worker count", async () => {
    const { getOrgInfo } = await import("@/lib/db");
    const info = getOrgInfo(dbPath);
    expect(info.name).toBe("test-org");
    expect(info.status).toBe("running");
    expect(info.worker_count).toBeGreaterThan(0);
  });

  it("returns ceo_worker_id", async () => {
    const { getOrgInfo } = await import("@/lib/db");
    const info = getOrgInfo(dbPath);
    expect(info.ceo_worker_id).toBe("worker-ceo-1");
  });

  it("counts active sessions", async () => {
    const { getOrgInfo } = await import("@/lib/db");
    const info = getOrgInfo(dbPath);
    expect(info.active_session_count).toBe(1);
  });
});

describe("getWorkers", () => {
  it("returns all workers", async () => {
    const { getWorkers } = await import("@/lib/db");
    const workers = getWorkers(dbPath);
    expect(workers).toHaveLength(2);
  });

  it("marks CEO correctly", async () => {
    const { getWorkers } = await import("@/lib/db");
    const workers = getWorkers(dbPath);
    const ceo = workers.find((w) => w.is_ceo);
    expect(ceo).toBeDefined();
    expect(ceo?.name).toBe("Alice");
  });

  it("includes session_state for each worker", async () => {
    const { getWorkers } = await import("@/lib/db");
    const workers = getWorkers(dbPath);
    const ceo = workers.find((w) => w.id === "worker-ceo-1");
    expect(ceo?.session_state).toBe("running");
  });

  it("includes team_name", async () => {
    const { getWorkers } = await import("@/lib/db");
    const workers = getWorkers(dbPath);
    expect(workers[0].team_name).toBeTruthy();
  });
});

describe("getMessages", () => {
  it("returns messages from board channel", async () => {
    const { getMessages } = await import("@/lib/db");
    const msgs = getMessages(dbPath, "board-channel");
    expect(msgs.length).toBeGreaterThan(0);
  });

  it("includes sender name", async () => {
    const { getMessages } = await import("@/lib/db");
    const msgs = getMessages(dbPath, "board-channel");
    expect(msgs[0].from_worker_name).toBeTruthy();
  });

  it("sorts messages chronologically (oldest first)", async () => {
    const { getMessages } = await import("@/lib/db");
    const msgs = getMessages(dbPath, "board-channel");
    if (msgs.length > 1) {
      expect(new Date(msgs[0].created_at).getTime()).toBeLessThanOrEqual(new Date(msgs[msgs.length - 1].created_at).getTime());
    }
  });
});

describe("sendReply", () => {
  it("inserts a new message to the channel when replying to an existing message", async () => {
    const { sendReply, getMessages } = await import("@/lib/db");
    const before = getMessages(dbPath, "board-channel");
    // msg-1 exists in fixture; CEO (worker-ceo-1) is the org CEO
    sendReply(dbPath, "msg-1", "Acknowledged, continuing");
    const after = getMessages(dbPath, "board-channel");
    expect(after.length).toBe(before.length + 1);
  });
});

describe("getOKRs", () => {
  it("returns all OKRs", async () => {
    const { getOKRs } = await import("@/lib/db");
    const okrs = getOKRs(dbPath);
    expect(okrs.length).toBe(2);
  });

  it("parses key_results JSON", async () => {
    const { getOKRs } = await import("@/lib/db");
    const okrs = getOKRs(dbPath);
    const okr = okrs.find((o) => o.id === "okr-1");
    expect(Array.isArray(okr?.key_results)).toBe(true);
    expect(okr?.key_results[0].title).toBe("Outreach calls");
  });

  it("includes owner_name", async () => {
    const { getOKRs } = await import("@/lib/db");
    const okrs = getOKRs(dbPath);
    const root = okrs.find((o) => o.parent_id === null);
    expect(root?.owner_name).toBe("Alice");
  });

  it("tracks children_count", async () => {
    const { getOKRs } = await import("@/lib/db");
    const okrs = getOKRs(dbPath);
    const root = okrs.find((o) => o.id === "okr-1");
    expect(root?.children_count).toBe(1);
  });
});

describe("getBudgetSummary", () => {
  it("returns spend_today", async () => {
    const { getBudgetSummary } = await import("@/lib/db");
    const budget = getBudgetSummary(dbPath);
    expect(typeof budget.spend_today).toBe("number");
    expect(budget.spend_today).toBeGreaterThan(0);
  });
});

describe("getRecentActivity", () => {
  it("returns an array (may be empty if no status changes)", async () => {
    const { getRecentActivity } = await import("@/lib/db");
    const activity = getRecentActivity(dbPath);
    expect(Array.isArray(activity)).toBe(true);
  });
});

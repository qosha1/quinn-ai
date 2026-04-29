import Database from "better-sqlite3";
import fs from "fs";
import path from "path";
import type {
  OrgInfo,
  WorkerInfo,
  BudgetSummary,
  HealthStatus,
  HealthIssue,
  Message,
  OKRInfo,
  KeyResult,
  ActivityEntry,
} from "./types";

interface CachedConnection {
  db: Database.Database;
  lastAccess: number;
}

const MAX_CACHE_SIZE = 5;
const CONNECTION_TTL_MS = 5 * 60 * 1000;
const connectionCache = new Map<string, CachedConnection>();

function getConnection(dbPath: string): Database.Database {
  const now = Date.now();
  const cached = connectionCache.get(dbPath);
  if (cached) {
    cached.lastAccess = now;
    return cached.db;
  }

  for (const [key, conn] of connectionCache.entries()) {
    if (now - conn.lastAccess > CONNECTION_TTL_MS) {
      try { conn.db.close(); } catch { /* ignore */ }
      connectionCache.delete(key);
    }
  }

  if (connectionCache.size >= MAX_CACHE_SIZE) {
    let oldestKey = "";
    let oldestTime = Infinity;
    for (const [key, conn] of connectionCache.entries()) {
      if (conn.lastAccess < oldestTime) { oldestTime = conn.lastAccess; oldestKey = key; }
    }
    if (oldestKey) {
      try { connectionCache.get(oldestKey)?.db.close(); } catch { /* ignore */ }
      connectionCache.delete(oldestKey);
    }
  }

  const db = new Database(dbPath, { readonly: false });
  db.pragma("journal_mode = WAL");
  connectionCache.set(dbPath, { db, lastAccess: now });
  return db;
}

function cleanup(): void {
  for (const conn of connectionCache.values()) {
    try { conn.db.close(); } catch { /* ignore */ }
  }
  connectionCache.clear();
}

if (typeof process !== "undefined") {
  process.on("exit", cleanup);
  process.on("SIGINT", () => { cleanup(); process.exit(0); });
  process.on("SIGTERM", () => { cleanup(); process.exit(0); });
}

export function resolveDbPath(startDir?: string): string {
  const envPath = process.env.QUINN_DB_PATH;
  if (envPath && fs.existsSync(envPath)) return envPath;

  const base = startDir ?? process.cwd();
  const candidates = [
    path.join(base, "live", "quinn.db"),
    path.join(base, "..", "live", "quinn.db"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  throw new Error(`quinn.db not found. Set QUINN_DB_PATH or run from org directory. Searched: ${candidates.join(", ")}`);
}

export function getOrgInfo(dbPath: string): OrgInfo {
  const db = getConnection(dbPath);

  const org = db.prepare(`
    SELECT name, status, ceo_worker_id, started_at, stopped_at
    FROM org_state WHERE id = 'default'
  `).get() as { name: string; status: string; ceo_worker_id: string | null; started_at: string | null; stopped_at: string | null } | undefined;

  if (!org) throw new Error("No org_state found");

  const workerCount = (db.prepare("SELECT COUNT(*) as n FROM workers WHERE status NOT IN ('terminated','offboarding')").get() as { n: number }).n;
  const activeSessionCount = (db.prepare("SELECT COUNT(*) as n FROM sessions WHERE state IN ('running','starting','idle')").get() as { n: number }).n;

  return {
    name: org.name,
    status: org.status as OrgInfo["status"],
    ceo_worker_id: org.ceo_worker_id,
    worker_count: workerCount,
    active_session_count: activeSessionCount,
    started_at: org.started_at,
    stopped_at: org.stopped_at,
  };
}

export function getWorkers(dbPath: string): WorkerInfo[] {
  const db = getConnection(dbPath);

  const rows = db.prepare(`
    SELECT
      w.id,
      w.name,
      w.role,
      w.status,
      w.manager_id,
      COALESCE(t.name, '') as team_name,
      COALESCE(ws.runtime_status, 'stopped') as runtime_status,
      ws.current_task_id,
      s.state as session_state,
      o.ceo_worker_id
    FROM workers w
    LEFT JOIN teams t ON w.team_id = t.id
    LEFT JOIN worker_state ws ON w.id = ws.worker_id
    LEFT JOIN sessions s ON w.id = s.worker_id AND s.state IN ('running','starting','idle')
    LEFT JOIN org_state o ON o.id = 'default'
    WHERE w.status NOT IN ('terminated')
    GROUP BY w.id
    ORDER BY CASE w.role WHEN 'CEO' THEN 0 WHEN 'Director' THEN 1 WHEN 'Manager' THEN 2 ELSE 3 END, w.name
  `).all() as Array<{
    id: string;
    name: string;
    role: string;
    status: string;
    manager_id: string | null;
    team_name: string;
    runtime_status: string;
    current_task_id: string | null;
    session_state: string | null;
    ceo_worker_id: string | null;
  }>;

  return rows.map((row) => ({
    id: row.id,
    name: row.name,
    role: row.role.toLowerCase() as WorkerInfo["role"],
    team_name: row.team_name,
    status: row.status as WorkerInfo["status"],
    session_state: (row.session_state ?? row.runtime_status) as WorkerInfo["session_state"],
    manager_id: row.manager_id,
    current_task: row.current_task_id,
    is_ceo: row.id === row.ceo_worker_id,
  }));
}

export function getMessages(dbPath: string, channelName: string = "board-channel"): Message[] {
  const db = getConnection(dbPath);

  const rows = db.prepare(`
    SELECT
      m.id,
      m.from_worker_id,
      COALESCE(w.name, m.from_worker_id) as from_worker_name,
      c.name as channel_name,
      m.content,
      m.priority,
      m.created_at,
      CASE WHEN nb.read_at IS NOT NULL OR nb.actioned_at IS NOT NULL THEN 1 ELSE 0 END as is_read
    FROM messages m
    JOIN channels c ON m.channel_id = c.id
    LEFT JOIN workers w ON m.from_worker_id = w.id
    LEFT JOIN notification_beads nb ON nb.message_id = m.id
    WHERE c.name = ?
    GROUP BY m.id
    ORDER BY m.priority ASC, m.created_at DESC
    LIMIT 100
  `).all(channelName) as Array<{
    id: string;
    from_worker_id: string;
    from_worker_name: string;
    channel_name: string;
    content: string;
    priority: number;
    created_at: string;
    is_read: number;
  }>;

  return rows.map((row) => ({
    id: row.id,
    from_worker_id: row.from_worker_id,
    from_worker_name: row.from_worker_name,
    channel_name: row.channel_name,
    content: row.content,
    priority: row.priority as Message["priority"],
    created_at: row.created_at,
    is_read: row.is_read === 1,
  }));
}

export function getAllChannels(dbPath: string): Array<{ id: string; name: string; channel_type: string }> {
  const db = getConnection(dbPath);
  return (db.prepare("SELECT id, name, type as channel_type FROM channels ORDER BY name").all() as Array<{ id: string; name: string; channel_type: string }>);
}

export function markMessageRead(dbPath: string, messageId: string): void {
  const db = getConnection(dbPath);
  db.prepare(`
    UPDATE notification_beads SET read_at = datetime('now') WHERE message_id = ? AND read_at IS NULL
  `).run(messageId);
}

export function sendReply(dbPath: string, originalMessageId: string, content: string): string {
  const db = getConnection(dbPath);

  const orig = db.prepare("SELECT channel_id, thread_id FROM messages WHERE id = ?").get(originalMessageId) as { channel_id: string; thread_id: string | null } | undefined;
  const ceo = db.prepare("SELECT ceo_worker_id FROM org_state WHERE id = 'default'").get() as { ceo_worker_id: string } | undefined;
  if (!ceo?.ceo_worker_id) throw new Error("No CEO worker found to send reply as");

  const channelId = orig?.channel_id ?? (db.prepare("SELECT id FROM channels WHERE name = 'board-channel' LIMIT 1").get() as { id: string } | undefined)?.id;
  if (!channelId) throw new Error("No channel found for reply");

  const threadId = orig?.thread_id ?? originalMessageId;
  const id = `msg-board-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  db.prepare(`
    INSERT INTO messages (id, channel_id, thread_id, parent_id, from_worker_id, content, priority, time_sensitivity)
    VALUES (?, ?, ?, ?, ?, ?, 3, 'immediate')
  `).run(id, channelId, threadId, originalMessageId, ceo.ceo_worker_id, content);
  return id;
}

export function getOKRs(dbPath: string, ownerId?: string): OKRInfo[] {
  const db = getConnection(dbPath);

  const query = ownerId
    ? `SELECT o.*, COALESCE(w.name, o.owner_worker_id) as owner_name,
         (SELECT COUNT(*) FROM okrs c WHERE c.parent_okr_id = o.id) as children_count
       FROM okrs o LEFT JOIN workers w ON o.owner_worker_id = w.id
       WHERE o.owner_worker_id = ? AND o.status != 'cancelled'
       ORDER BY o.created_at ASC`
    : `SELECT o.*, COALESCE(w.name, o.owner_worker_id) as owner_name,
         (SELECT COUNT(*) FROM okrs c WHERE c.parent_okr_id = o.id) as children_count
       FROM okrs o LEFT JOIN workers w ON o.owner_worker_id = w.id
       WHERE o.status != 'cancelled'
       ORDER BY o.created_at ASC`;

  const rows = (ownerId ? db.prepare(query).all(ownerId) : db.prepare(query).all()) as Array<{
    id: string;
    title: string;
    description: string | null;
    owner_name: string;
    owner_worker_id: string;
    status: string;
    parent_okr_id: string | null;
    key_results: string;
    due_date: string | null;
    children_count: number;
  }>;

  return rows.map((row) => ({
    id: row.id,
    title: row.title,
    description: row.description,
    owner_name: row.owner_name,
    owner_id: row.owner_worker_id,
    status: row.status as OKRInfo["status"],
    parent_id: row.parent_okr_id,
    key_results: safeParseJSON<KeyResult[]>(row.key_results, []),
    due_date: row.due_date,
    children_count: row.children_count,
  }));
}

export function getBudgetSummary(dbPath: string): BudgetSummary {
  const db = getConnection(dbPath);

  const totals = db.prepare(`
    SELECT COALESCE(SUM(allocated_credits), 0) as total_allocated
    FROM budget_allocations
  `).get() as { total_allocated: number };

  const spendToday = (db.prepare(`
    SELECT COALESCE(SUM(ABS(amount)), 0) as n FROM budget_transactions
    WHERE type = 'spend' AND date(created_at) = date('now')
  `).get() as { n: number }).n;

  const spendWeek = (db.prepare(`
    SELECT COALESCE(SUM(ABS(amount)), 0) as n FROM budget_transactions
    WHERE type = 'spend' AND created_at >= datetime('now', '-7 days')
  `).get() as { n: number }).n;

  const totalSpent = (db.prepare(`
    SELECT COALESCE(SUM(ABS(amount)), 0) as n FROM budget_transactions
    WHERE type = 'spend'
  `).get() as { n: number }).n;

  return {
    total_allocated: totals.total_allocated,
    total_spent: totalSpent,
    total_available: totals.total_allocated - totalSpent,
    spend_today: spendToday,
    spend_this_week: spendWeek,
  };
}

export function getHealthStatus(dbPath: string): HealthStatus {
  const db = getConnection(dbPath);
  const issues: HealthIssue[] = [];

  const crashed = db.prepare(`
    SELECT w.id, w.name FROM workers w
    JOIN sessions s ON w.id = s.worker_id
    WHERE s.state = 'crashed' AND w.status = 'active'
  `).all() as Array<{ id: string; name: string }>;

  for (const w of crashed) {
    issues.push({ worker_id: w.id, worker_name: w.name, issue_type: "crashed_session", severity: "error", message: `${w.name}'s session has crashed` });
  }

  const noOKRs = db.prepare(`
    SELECT w.id, w.name FROM workers w
    WHERE w.status = 'active'
    AND w.id NOT IN (SELECT DISTINCT owner_worker_id FROM okrs WHERE status = 'active')
  `).all() as Array<{ id: string; name: string }>;

  for (const w of noOKRs) {
    issues.push({ worker_id: w.id, worker_name: w.name, issue_type: "no_okrs", severity: "warning", message: `${w.name} has no active OKRs` });
  }

  const totalWorkers = (db.prepare("SELECT COUNT(*) as n FROM workers WHERE status = 'active'").get() as { n: number }).n;
  const uniqueWorkerIds = new Set(issues.map((i) => i.worker_id));
  const score: HealthStatus["overall_score"] =
    crashed.length > 0 ? "critical" : issues.length > 0 ? "warning" : "healthy";

  return {
    overall_score: score,
    issues,
    workers_with_issues: uniqueWorkerIds.size,
    total_workers: totalWorkers,
  };
}

export function getRecentActivity(dbPath: string, limitMinutes: number = 60): ActivityEntry[] {
  const db = getConnection(dbPath);

  const rows = db.prepare(`
    SELECT
      sc.changed_at as timestamp,
      sc.entity_id as worker_id,
      COALESCE(w.name, sc.entity_id) as worker_name,
      sc.entity_type as event_type,
      (COALESCE(sc.old_status, '?') || ' → ' || sc.new_status) as summary
    FROM status_changes sc
    LEFT JOIN workers w ON sc.entity_id = w.id AND sc.entity_type = 'worker'
    WHERE sc.changed_at >= datetime('now', ? || ' minutes')
    ORDER BY sc.changed_at DESC
    LIMIT 50
  `).all(`-${limitMinutes}`) as ActivityEntry[];

  return rows;
}

function safeParseJSON<T>(raw: string, fallback: T): T {
  try { return JSON.parse(raw) as T; } catch { return fallback; }
}

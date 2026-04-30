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

  // Check if notification_beads table exists (may be missing in some fixtures)
  const hasNotifTable = (db.prepare(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='notification_beads'"
  ).get() as { name: string } | undefined) != null;

  const readExpr = hasNotifTable
    ? "CASE WHEN nb.read_at IS NOT NULL OR nb.actioned_at IS NOT NULL THEN 1 ELSE 0 END"
    : "0";
  const joinClause = hasNotifTable
    ? "LEFT JOIN notification_beads nb ON nb.message_id = m.id"
    : "";

  const rows = db.prepare(`
    SELECT
      m.id,
      m.from_worker_id,
      COALESCE(w.name, m.from_worker_id) as from_worker_name,
      c.name as channel_name,
      m.content,
      m.priority,
      m.created_at,
      ${readExpr} as is_read
    FROM messages m
    JOIN channels c ON m.channel_id = c.id
    LEFT JOIN workers w ON m.from_worker_id = w.id
    ${joinClause}
    WHERE c.name = ?
    GROUP BY m.id
    ORDER BY m.created_at ASC
    LIMIT 200
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

export function getAllChannels(dbPath: string): Array<{ id: string; name: string; channel_type: string; message_count: number; unread_count: number }> {
  const db = getConnection(dbPath);
  return (db.prepare(`
    SELECT
      c.id,
      c.name,
      c.type as channel_type,
      COUNT(m.id) as message_count,
      SUM(CASE WHEN nb.read_at IS NULL AND nb.actioned_at IS NULL AND m.id IS NOT NULL THEN 1 ELSE 0 END) as unread_count
    FROM channels c
    LEFT JOIN messages m ON c.id = m.channel_id
    LEFT JOIN notification_beads nb ON nb.message_id = m.id
    GROUP BY c.id
    HAVING COUNT(m.id) > 0
    ORDER BY MAX(m.created_at) DESC
  `).all() as Array<{ id: string; name: string; channel_type: string; message_count: number; unread_count: number }>);
}

export function markMessageRead(dbPath: string, messageId: string): void {
  const db = getConnection(dbPath);
  db.prepare(`
    UPDATE notification_beads SET read_at = datetime('now') WHERE message_id = ? AND read_at IS NULL
  `).run(messageId);
}

export interface PostedMessage {
  id: string;
  channel_id: string;
  thread_id: string | null;
  parent_id: string | null;
  from_worker_id: string;
  content: string;
}

export function postMessageToChannel(
  dbPath: string,
  channelId: string,
  fromWorkerId: string,
  content: string,
  priority: number = 2,
): PostedMessage {
  const db = getConnection(dbPath);
  const id = `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  db.prepare(`
    INSERT INTO messages (id, channel_id, thread_id, parent_id, from_worker_id, content, priority, time_sensitivity)
    VALUES (?, ?, NULL, NULL, ?, ?, ?, 'whenever')
  `).run(id, channelId, fromWorkerId, content, priority);
  return { id, channel_id: channelId, thread_id: null, parent_id: null, from_worker_id: fromWorkerId, content };
}

export function getThreadMessages(dbPath: string, threadId: string): Message[] {
  const db = getConnection(dbPath);
  const rows = db.prepare(`
    SELECT
      m.id, m.from_worker_id,
      COALESCE(w.name, m.from_worker_id) as from_worker_name,
      c.name as channel_name,
      m.content, m.priority, m.created_at,
      m.thread_id, m.parent_id,
      0 as is_read
    FROM messages m
    JOIN channels c ON m.channel_id = c.id
    LEFT JOIN workers w ON m.from_worker_id = w.id
    WHERE m.thread_id = ?
    ORDER BY m.created_at ASC
  `).all(threadId) as Array<{
    id: string; from_worker_id: string; from_worker_name: string;
    channel_name: string; content: string; priority: number;
    created_at: string; thread_id: string | null; parent_id: string | null; is_read: number;
  }>;
  return rows.map((r) => ({ ...r, is_read: r.is_read === 1, priority: r.priority as Message["priority"] }));
}

export function markChannelRead(dbPath: string, channelName: string): void {
  const db = getConnection(dbPath);
  db.prepare(`
    UPDATE notification_beads SET read_at = datetime('now')
    WHERE read_at IS NULL
    AND message_id IN (
      SELECT m.id FROM messages m
      JOIN channels c ON m.channel_id = c.id
      WHERE c.name = ?
    )
  `).run(channelName);
}

export function searchMessages(
  dbPath: string,
  query: string,
  channelFilter?: string,
): Array<{ id: string; from_worker_name: string; channel_name: string; content: string; created_at: string }> {
  const db = getConnection(dbPath);
  // Use LIKE since FTS5 is set up in CLI but may not be in all fixture DBs
  const sql = channelFilter
    ? `SELECT m.id, COALESCE(w.name, m.from_worker_id) as from_worker_name,
         c.name as channel_name, m.content, m.created_at
       FROM messages m JOIN channels c ON m.channel_id = c.id
       LEFT JOIN workers w ON m.from_worker_id = w.id
       WHERE m.content LIKE ? AND c.name = ?
       ORDER BY m.created_at DESC LIMIT 50`
    : `SELECT m.id, COALESCE(w.name, m.from_worker_id) as from_worker_name,
         c.name as channel_name, m.content, m.created_at
       FROM messages m JOIN channels c ON m.channel_id = c.id
       LEFT JOIN workers w ON m.from_worker_id = w.id
       WHERE m.content LIKE ?
       ORDER BY m.created_at DESC LIMIT 50`;
  const like = `%${query}%`;
  return (channelFilter
    ? db.prepare(sql).all(like, channelFilter)
    : db.prepare(sql).all(like)) as Array<{ id: string; from_worker_name: string; channel_name: string; content: string; created_at: string }>;
}

export function subscribeToChannel(dbPath: string, channelId: string, workerId: string): void {
  const db = getConnection(dbPath);
  db.prepare(`
    INSERT OR IGNORE INTO channel_subscriptions (channel_id, worker_id)
    VALUES (?, ?)
  `).run(channelId, workerId);
}

export function unsubscribeFromChannel(dbPath: string, channelId: string, workerId: string): void {
  const db = getConnection(dbPath);
  db.prepare(`DELETE FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?`).run(channelId, workerId);
}

export function getChannelsWithSubscription(
  dbPath: string,
  workerId: string,
): Array<{ id: string; name: string; channel_type: string; subscribed: boolean }> {
  const db = getConnection(dbPath);
  return (db.prepare(`
    SELECT c.id, c.name, c.type as channel_type,
      CASE WHEN cs.worker_id IS NOT NULL THEN 1 ELSE 0 END as subscribed
    FROM channels c
    LEFT JOIN channel_subscriptions cs ON c.id = cs.channel_id AND cs.worker_id = ?
    ORDER BY c.name
  `).all(workerId) as Array<{ id: string; name: string; channel_type: string; subscribed: number }>)
    .map((r) => ({ ...r, subscribed: r.subscribed === 1 }));
}

export function createDirectChannel(
  dbPath: string,
  worker1Id: string,
  worker2Id: string,
): string {
  const db = getConnection(dbPath);
  const sorted = [worker1Id, worker2Id].sort();
  const name = `dm-${sorted[0].slice(0, 8)}-${sorted[1].slice(0, 8)}`;

  const existing = db.prepare("SELECT id FROM channels WHERE name = ?").get(name) as { id: string } | undefined;
  if (existing) return existing.id;

  const id = `chan-dm-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  db.prepare(`INSERT INTO channels (id, name, type) VALUES (?, ?, 'direct')`).run(id, name);
  // Subscribe both workers — try the real schema table, fall back to fixture alias
  const subTable = (db.prepare(
    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('channel_subscriptions','channel_members') LIMIT 1"
  ).get() as { name: string } | undefined)?.name;
  if (subTable) {
    try {
      db.prepare(`INSERT OR IGNORE INTO ${subTable} (channel_id, worker_id) VALUES (?, ?)`).run(id, worker1Id);
      db.prepare(`INSERT OR IGNORE INTO ${subTable} (channel_id, worker_id) VALUES (?, ?)`).run(id, worker2Id);
    } catch { /* ignore */ }
  }
  return id;
}

export function addReaction(dbPath: string, messageId: string, workerId: string, emoji: string): void {
  const db = getConnection(dbPath);
  db.prepare(`
    INSERT OR IGNORE INTO message_reactions (message_id, worker_id, emoji) VALUES (?, ?, ?)
  `).run(messageId, workerId, emoji);
}

export function removeReaction(dbPath: string, messageId: string, workerId: string, emoji: string): void {
  const db = getConnection(dbPath);
  db.prepare(`DELETE FROM message_reactions WHERE message_id = ? AND worker_id = ? AND emoji = ?`).run(messageId, workerId, emoji);
}

export function getReactionCounts(dbPath: string, messageId: string): Record<string, number> {
  const db = getConnection(dbPath);
  try {
    const rows = db.prepare(`
      SELECT emoji, COUNT(*) as count FROM message_reactions WHERE message_id = ? GROUP BY emoji
    `).all(messageId) as Array<{ emoji: string; count: number }>;
    return Object.fromEntries(rows.map((r) => [r.emoji, r.count]));
  } catch {
    return {};
  }
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
    created_at: string | null;
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
    created_at: row.created_at ?? null,
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

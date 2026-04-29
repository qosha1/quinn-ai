"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { WorkerRow } from "@/components/WorkerRow";
import { MessageItem } from "@/components/MessageItem";
import { OKRNode } from "@/components/OKRNode";
import { buildOKRTree, formatCurrency, formatRelativeTime } from "@/lib/transforms";
import type { OrgDashboard, WorkerInfo, Message, OKRInfo, ActivityEntry } from "@/lib/types";

type Tab = "dashboard" | "team" | "messages" | "okrs" | "activity";

interface Toast { id: number; message: string; type: "success" | "error" }

const POLL_INTERVAL = 15000;

async function fetchWithRetry<T>(url: string, opts?: RequestInit, retries = 2): Promise<T> {
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await fetch(url, opts);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return await res.json() as T;
    } catch (err) {
      if (i === retries) throw err;
      await new Promise((r) => setTimeout(r, 1000 * (i + 1)));
    }
  }
  throw new Error("unreachable");
}

export default function BoardPage() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [dashboard, setDashboard] = useState<OrgDashboard | null>(null);
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [okrs, setOKRs] = useState<OKRInfo[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [selectedMsg, setSelectedMsg] = useState<Message | null>(null);
  const [replyText, setReplyText] = useState("");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toastIdRef = useRef(0);
  const prevWorkersRef = useRef<WorkerInfo[]>([]);

  const toast = useCallback((message: string, type: "success" | "error" = "success") => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);

  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setPolling(true);
    try {
      const [db, ws, msgs, os, act] = await Promise.all([
        fetchWithRetry<OrgDashboard>("/api/org"),
        fetchWithRetry<{ workers: WorkerInfo[] }>("/api/workers"),
        fetchWithRetry<{ messages: Message[] }>("/api/messages?channel=board-channel"),
        fetchWithRetry<{ okrs: OKRInfo[] }>("/api/okrs"),
        fetchWithRetry<{ activity: ActivityEntry[] }>("/api/activity"),
      ]);
      setDashboard(db);
      setWorkers(ws.workers);
      setMessages(msgs.messages);
      setOKRs(os.okrs);
      setActivity(act.activity);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
      setPolling(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  useEffect(() => {
    const interval = setInterval(() => fetchAll(true), POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleWorkerAction = useCallback(async (workerId: string, action: "pause" | "resume" | "fire") => {
    prevWorkersRef.current = workers;
    const label = action === "fire" ? "Firing" : action === "pause" ? "Pausing" : "Resuming";
    toast(`${label} worker…`);
    try {
      await fetchWithRetry(`/api/workers/${workerId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      toast(`Worker ${action}d`, "success");
      fetchAll(true);
    } catch (err) {
      toast(`Failed: ${err}`, "error");
      setWorkers(prevWorkersRef.current);
    }
  }, [workers, toast, fetchAll]);

  const handleReply = useCallback(async (messageId: string) => {
    if (!replyText.trim() || !selectedMsg) return;
    try {
      await fetchWithRetry(`/api/messages/${messageId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: replyText }),
      });
      toast("Reply sent", "success");
      setReplyText("");
      setSelectedMsg(null);
      fetchAll(true);
    } catch (err) {
      toast(`Failed to send reply: ${err}`, "error");
    }
  }, [replyText, messages, toast, fetchAll]);

  const handleMarkRead = useCallback(async (messageId: string) => {
    setMessages((prev) => prev.map((m) => m.id === messageId ? { ...m, is_read: true } : m));
    try {
      await fetch(`/api/messages/${messageId}`, { method: "PATCH" });
    } catch {
      setMessages((prev) => prev.map((m) => m.id === messageId ? { ...m, is_read: false } : m));
    }
  }, []);

  const unreadCount = messages.filter((m) => !m.is_read).length;
  const orgTree = buildOKRTree(okrs);

  if (loading) {
    return (
      <div className="board-layout" style={{ justifyContent: "center", alignItems: "center" }}>
        <div><span className="spinner">⟳</span> Loading QuinnAI Board…</div>
      </div>
    );
  }

  if (error && !dashboard) {
    return (
      <div className="board-layout" style={{ justifyContent: "center", alignItems: "center", padding: "40px" }}>
        <div>
          <div style={{ color: "var(--red)", marginBottom: "12px" }}>Failed to connect to org database</div>
          <div style={{ color: "var(--fg-muted)", fontSize: "13px", marginBottom: "16px" }}>{error}</div>
          <button onClick={() => fetchAll()}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="board-layout">
      {/* Header */}
      <header className="board-header">
        <span className="board-header__title">QuinnAI Board</span>
        {dashboard && (
          <>
            <span className="board-header__org">{dashboard.org.name}</span>
            <span className={`org-status-badge org-status-badge--${
              dashboard.health.overall_score === "critical" ? "critical" :
              dashboard.health.overall_score === "warning" ? "warning" :
              dashboard.org.status
            }`}>
              {dashboard.health.overall_score === "critical" ? "⚠ Critical" :
               dashboard.health.overall_score === "warning" ? "⚠ Warning" :
               dashboard.org.status}
            </span>
          </>
        )}
        <span className="poll-dot" title="auto-refresh" />
        <span style={{ marginLeft: "auto", color: "var(--fg-muted)", fontSize: "12px" }}>
          refreshes every {POLL_INTERVAL / 1000}s
        </span>
        <button style={{ fontSize: "12px", padding: "2px 10px" }} onClick={() => fetchAll(true)}>
          ↺ Refresh
        </button>
      </header>

      {/* Tab bar */}
      <nav className="tab-bar">
        {(["dashboard", "team", "messages", "okrs", "activity"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`tab ${tab === t ? "tab--active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t === "messages" && unreadCount > 0 ? `Messages (${unreadCount})` : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <main className="tab-content">

        {/* ── DASHBOARD ── */}
        {tab === "dashboard" && dashboard && (
          <div>
            <div className="dashboard-grid">
              <div className="stat-card">
                <div className="stat-card__label">Workers</div>
                <div className="stat-card__value">{dashboard.org.worker_count}</div>
                <div className="stat-card__sub">{dashboard.org.active_session_count} active sessions</div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Spend Today</div>
                <div className="stat-card__value">{formatCurrency(dashboard.budget.spend_today)}</div>
                <div className="stat-card__sub">{formatCurrency(dashboard.budget.spend_this_week)} this week</div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Budget Available</div>
                <div className="stat-card__value">{formatCurrency(dashboard.budget.total_available)}</div>
                <div className="stat-card__sub">of {formatCurrency(dashboard.budget.total_allocated)} allocated</div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Messages</div>
                <div className="stat-card__value">{unreadCount}</div>
                <div className="stat-card__sub">unread in board channel</div>
              </div>
            </div>

            {dashboard.health.issues.length > 0 && (
              <div className="health-panel">
                <div className="health-panel__title">Health Issues</div>
                {dashboard.health.issues.map((issue, i) => (
                  <div key={i} className={`health-issue health-issue--${issue.severity}`}>
                    <span className="health-issue__icon">{issue.severity === "error" ? "●" : "○"}</span>
                    <span className="health-issue__message">{issue.message}</span>
                  </div>
                ))}
              </div>
            )}

            {dashboard.org.started_at && (
              <div style={{ color: "var(--fg-muted)", fontSize: "12px" }}>
                Started {formatRelativeTime(dashboard.org.started_at)}
                {dashboard.org.ceo_worker_id && ` · CEO: ${workers.find((w) => w.id === dashboard.org.ceo_worker_id)?.name ?? dashboard.org.ceo_worker_id}`}
              </div>
            )}
          </div>
        )}

        {/* ── TEAM ── */}
        {tab === "team" && (
          <div>
            <div className="section-title" style={{ marginBottom: "16px" }}>
              {workers.length} workers
            </div>
            <table className="workers-table">
              <thead>
                <tr>
                  <th style={{ width: 24 }}></th>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Team</th>
                  <th>Status</th>
                  <th style={{ width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {workers.map((w) => (
                  <WorkerRow key={w.id} worker={w} onAction={handleWorkerAction} />
                ))}
                {workers.length === 0 && (
                  <tr><td colSpan={6} className="empty-state">No workers found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* ── MESSAGES ── */}
        {tab === "messages" && (
          <div className="messages-layout" style={{ margin: "-20px" }}>
            <div className="messages-list">
              {messages.length === 0 && <div className="empty-state">No messages</div>}
              {messages.map((msg) => (
                <MessageItem
                  key={msg.id}
                  message={msg}
                  isSelected={selectedMsg?.id === msg.id}
                  onClick={() => { setSelectedMsg(msg); setReplyText(""); }}
                  onReply={(id) => { setSelectedMsg(messages.find((m) => m.id === id) ?? null); }}
                  onMarkRead={handleMarkRead}
                />
              ))}
            </div>
            <div className="messages-detail">
              {selectedMsg ? (
                <div>
                  <div className="message-detail__header">
                    <div className="message-detail__from">{selectedMsg.from_worker_name}</div>
                    <div className="message-detail__meta">
                      {selectedMsg.channel_name} · {formatRelativeTime(selectedMsg.created_at)}
                    </div>
                  </div>
                  <div className="message-detail__content">{selectedMsg.content}</div>
                  <div className="reply-area">
                    <div className="reply-area__label">Reply</div>
                    <textarea
                      rows={5}
                      placeholder="Type your response…"
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleReply(selectedMsg.id);
                      }}
                    />
                    <div className="reply-area__actions">
                      <button className="btn-sm btn-sm--ghost" onClick={() => { setSelectedMsg(null); setReplyText(""); }}>Cancel</button>
                      <button onClick={() => handleReply(selectedMsg.id)} disabled={!replyText.trim()}>Send reply ⌘↵</button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="empty-state">Select a message to view and reply</div>
              )}
            </div>
          </div>
        )}

        {/* ── OKRs ── */}
        {tab === "okrs" && (
          <div>
            <div className="section-title" style={{ marginBottom: "16px" }}>{okrs.length} OKRs</div>
            {orgTree.length === 0 && <div className="empty-state">No active OKRs</div>}
            {orgTree.map((node) => (
              <OKRNode key={node.id} node={node} depth={0} />
            ))}
          </div>
        )}

        {/* ── ACTIVITY ── */}
        {tab === "activity" && (
          <div>
            <div className="section-title" style={{ marginBottom: "16px" }}>Recent activity (last 60 min)</div>
            {activity.length === 0 && <div className="empty-state">No recent activity</div>}
            <div className="activity-list">
              {activity.map((entry, i) => (
                <div key={i} className="activity-item">
                  <span className="activity-item__time">{formatRelativeTime(entry.timestamp)}</span>
                  <span className="activity-item__worker">{entry.worker_name}</span>
                  <span className="activity-item__summary">{entry.summary}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Toasts */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.type}`}>{t.message}</div>
        ))}
      </div>
    </div>
  );
}

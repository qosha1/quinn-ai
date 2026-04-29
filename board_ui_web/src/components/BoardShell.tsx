"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { WorkerRow } from "@/components/WorkerRow";
import { MessageItem } from "@/components/MessageItem";
import { OKRNode } from "@/components/OKRNode";
import { buildOKRTree, formatCurrency, formatRelativeTime } from "@/lib/transforms";
import type { OrgDashboard, WorkerInfo, Message, OKRInfo, ActivityEntry, Channel } from "@/lib/types";

export type Tab = "dashboard" | "team" | "messages" | "okrs" | "activity";

interface Toast { id: number; message: string; type: "success" | "error" }

const POLL_INTERVAL = 15000;
const TABS: Tab[] = ["dashboard", "team", "messages", "okrs", "activity"];

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

interface Props {
  tab: Tab;
}

export function BoardShell({ tab }: Props) {
  const router = useRouter();
  const [dashboard, setDashboard] = useState<OrgDashboard | null>(null);
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [activeChannel, setActiveChannel] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [okrs, setOKRs] = useState<OKRInfo[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [selectedMsg, setSelectedMsg] = useState<Message | null>(null);
  const [replyText, setReplyText] = useState("");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toastIdRef = useRef(0);
  const prevWorkersRef = useRef<WorkerInfo[]>([]);

  const toast = useCallback((message: string, type: "success" | "error" = "success") => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);

  const fetchMessages = useCallback(async (channelName: string) => {
    try {
      const data = await fetchWithRetry<{ messages: Message[] }>(`/api/messages?channel=${encodeURIComponent(channelName)}`);
      setMessages(data.messages);
    } catch { /* silent */ }
  }, []);

  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [db, ws, chans, os, act] = await Promise.all([
        fetchWithRetry<OrgDashboard>("/api/org"),
        fetchWithRetry<{ workers: WorkerInfo[] }>("/api/workers"),
        fetchWithRetry<{ channels: Channel[] }>("/api/messages?channel=_channels"),
        fetchWithRetry<{ okrs: OKRInfo[] }>("/api/okrs"),
        fetchWithRetry<{ activity: ActivityEntry[] }>("/api/activity"),
      ]);
      setDashboard(db);
      setWorkers(ws.workers);
      setChannels(chans.channels);
      setOKRs(os.okrs);
      setActivity(act.activity);
      setError(null);

      // Auto-select first channel with messages if none selected
      if (chans.channels.length > 0) {
        setActiveChannel((prev) => {
          const chan = prev ?? chans.channels[0].name;
          fetchMessages(chan);
          return chan;
        });
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [fetchMessages]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  useEffect(() => {
    const interval = setInterval(() => fetchAll(true), POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleChannelSelect = useCallback((channelName: string) => {
    setActiveChannel(channelName);
    setSelectedMsg(null);
    setReplyText("");
    fetchMessages(channelName);
  }, [fetchMessages]);

  const handleWorkerAction = useCallback(async (workerId: string, action: "pause" | "resume" | "fire") => {
    prevWorkersRef.current = workers;
    toast(`${action.charAt(0).toUpperCase() + action.slice(1)}ing worker…`);
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
      if (activeChannel) fetchMessages(activeChannel);
    } catch (err) {
      toast(`Failed: ${err}`, "error");
    }
  }, [replyText, selectedMsg, activeChannel, toast, fetchMessages]);

  const handleMarkRead = useCallback(async (messageId: string) => {
    setMessages((prev) => prev.map((m) => m.id === messageId ? { ...m, is_read: true } : m));
    try {
      await fetch(`/api/messages/${messageId}`, { method: "PATCH" });
    } catch {
      setMessages((prev) => prev.map((m) => m.id === messageId ? { ...m, is_read: false } : m));
    }
  }, []);

  const totalUnread = channels.reduce((sum, c) => sum + (c.unread_count ?? 0), 0);
  const orgTree = buildOKRTree(okrs);

  if (loading) {
    return (
      <div className="board-layout" style={{ justifyContent: "center", alignItems: "center" }}>
        <span className="spinner">⟳</span> Loading…
      </div>
    );
  }

  if (error && !dashboard) {
    return (
      <div className="board-layout" style={{ justifyContent: "center", alignItems: "center", padding: 40 }}>
        <div style={{ color: "var(--red)", marginBottom: 8 }}>Failed to connect to org database</div>
        <div style={{ color: "var(--fg-muted)", fontSize: 13, marginBottom: 16 }}>{error}</div>
        <button onClick={() => fetchAll()}>Retry</button>
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
               dashboard.health.overall_score === "warning" ? `⚠ Warning (${dashboard.health.workers_with_issues})` :
               dashboard.org.status}
            </span>
          </>
        )}
        <span style={{ marginLeft: "auto", color: "var(--fg-muted)", fontSize: 12 }}>
          refreshes every {POLL_INTERVAL / 1000}s
        </span>
        <button style={{ fontSize: 12, padding: "2px 10px" }} onClick={() => fetchAll(true)}>↺ Refresh</button>
      </header>

      {/* Tab bar */}
      <nav className="tab-bar">
        {TABS.map((t) => (
          <button
            key={t}
            className={`tab ${tab === t ? "tab--active" : ""}`}
            onClick={() => router.push(`/${t}`)}
          >
            {t === "messages" && totalUnread > 0
              ? `Messages (${totalUnread})`
              : t.charAt(0).toUpperCase() + t.slice(1)}
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
                <div className="stat-card__label">Channels</div>
                <div className="stat-card__value">{channels.length}</div>
                <div className="stat-card__sub">{totalUnread > 0 ? `${totalUnread} unread` : "all read"}</div>
              </div>
            </div>

            {dashboard.health.issues.length > 0 && (
              <div className="health-panel">
                <div className="health-panel__title">Health Issues ({dashboard.health.workers_with_issues}/{dashboard.health.total_workers} workers)</div>
                {dashboard.health.issues.map((issue, i) => (
                  <div key={i} className={`health-issue health-issue--${issue.severity}`}>
                    <span className="health-issue__icon">{issue.severity === "error" ? "●" : "○"}</span>
                    <span className="health-issue__message">{issue.message}</span>
                  </div>
                ))}
              </div>
            )}

            {dashboard.org.started_at && (
              <div style={{ color: "var(--fg-muted)", fontSize: 12 }}>
                Started {formatRelativeTime(dashboard.org.started_at)}
                {dashboard.org.ceo_worker_id && ` · CEO: ${workers.find((w) => w.id === dashboard.org.ceo_worker_id)?.name ?? dashboard.org.ceo_worker_id}`}
              </div>
            )}
          </div>
        )}

        {/* ── TEAM ── */}
        {tab === "team" && (
          <div>
            <div className="section-title" style={{ marginBottom: 16 }}>{workers.length} workers</div>
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
            {/* Channel sidebar */}
            <div className="channel-sidebar">
              <div className="channel-sidebar__header">Channels</div>
              {channels.length === 0 && <div className="empty-state" style={{ padding: 16 }}>No messages yet</div>}
              {channels.map((ch) => (
                <button
                  key={ch.id}
                  className={`channel-item ${activeChannel === ch.name ? "channel-item--active" : ""}`}
                  onClick={() => handleChannelSelect(ch.name)}
                >
                  <span className="channel-item__icon">{ch.channel_type === "direct" || ch.name.startsWith("dm-") ? "◎" : "#"}</span>
                  <span className="channel-item__name">{ch.name.startsWith("dm-") ? formatDmName(ch.name, workers) : ch.name}</span>
                  {ch.unread_count > 0 && <span className="channel-item__badge">{ch.unread_count}</span>}
                  <span className="channel-item__count">{ch.message_count}</span>
                </button>
              ))}
            </div>

            {/* Message list */}
            <div className="messages-list">
              {messages.length === 0 && activeChannel && (
                <div className="empty-state">No messages in #{activeChannel}</div>
              )}
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

            {/* Message detail */}
            <div className="messages-detail">
              {selectedMsg ? (
                <div>
                  <div className="message-detail__header">
                    <div className="message-detail__from">{selectedMsg.from_worker_name}</div>
                    <div className="message-detail__meta">
                      #{selectedMsg.channel_name} · {formatRelativeTime(selectedMsg.created_at)}
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
                      <button onClick={() => handleReply(selectedMsg.id)} disabled={!replyText.trim()}>Send ⌘↵</button>
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
            <div className="section-title" style={{ marginBottom: 16 }}>{okrs.length} OKRs</div>
            {orgTree.length === 0 && <div className="empty-state">No active OKRs</div>}
            {orgTree.map((node) => (
              <OKRNode key={node.id} node={node} depth={0} />
            ))}
          </div>
        )}

        {/* ── ACTIVITY ── */}
        {tab === "activity" && (
          <div>
            <div className="section-title" style={{ marginBottom: 16 }}>Recent activity (last 60 min)</div>
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

function formatDmName(channelName: string, workers: WorkerInfo[]): string {
  // dm-wrkr-XXX-wrkr-YYY → look up worker names
  const parts = channelName.match(/wrkr-([a-z0-9]+)/g);
  if (!parts || parts.length < 2) return channelName;
  const names = parts.map((p) => {
    const full = workers.find((w) => w.id.startsWith(p.replace("-", "-").slice(0, 12)));
    return full?.name ?? p;
  });
  return `DM: ${names.join(" ↔ ")}`;
}

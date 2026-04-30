"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { WorkerRow } from "@/components/WorkerRow";
import { WorkBoard } from "@/components/WorkBoard";
import { OKRTimeline } from "@/components/OKRTimeline";
import { formatCurrency, formatRelativeTime } from "@/lib/transforms";
import type { OrgDashboard, WorkerInfo, Message, OKRInfo, ActivityEntry, Channel } from "@/lib/types";
import type { Bead, Dependency } from "@/lib/beads-db";

export type Tab = "dashboard" | "team" | "messages" | "okrs" | "work" | "activity";

interface Toast { id: number; message: string; type: "success" | "error" }

const POLL_INTERVAL = 15000;
const TABS: Tab[] = ["dashboard", "team", "messages", "okrs", "work", "activity"];

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

function avatarColor(name: string): string {
  const colors = ["#58a6ff", "#3fb950", "#d29922", "#db6d28", "#f85149", "#a371f7", "#39d353", "#ffa657"];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xffffffff;
  return colors[Math.abs(hash) % colors.length];
}

function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const initial = name.charAt(0).toUpperCase();
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%",
      background: avatarColor(name),
      color: "#fff", fontWeight: 700, fontSize: size * 0.42,
      display: "flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0,
    }}>
      {initial}
    </div>
  );
}

function formatDmName(channelName: string, workers: WorkerInfo[]): string {
  const parts = channelName.match(/wrkr-([a-z0-9]+)/g);
  if (!parts || parts.length < 2) return channelName;
  const names = parts.map((p) => {
    const full = workers.find((w) => w.id.startsWith(p.slice(0, 12)));
    return full?.name ?? p;
  });
  return names.join(" · ");
}

function formatChannelLabel(ch: Channel, workers: WorkerInfo[]): string {
  if (ch.name.startsWith("dm-")) return formatDmName(ch.name, workers);
  return ch.name;
}

interface Props { tab: Tab }

export function BoardShell({ tab }: Props) {
  const router = useRouter();
  const [dashboard, setDashboard] = useState<OrgDashboard | null>(null);
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [activeChannel, setActiveChannel] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [okrs, setOKRs] = useState<OKRInfo[]>([]);
  const [beads, setBeads] = useState<Bead[]>([]);
  const [beadDeps, setBeadDeps] = useState<Dependency[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [replyText, setReplyText] = useState("");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const toastIdRef = useRef(0);
  const prevWorkersRef = useRef<WorkerInfo[]>([]);

  const toast = useCallback((msg: string, type: "success" | "error" = "success") => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, message: msg, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);

  const fetchMessages = useCallback(async (channelName: string, scrollToBottom = true) => {
    try {
      const data = await fetchWithRetry<{ messages: Message[] }>(`/api/messages?channel=${encodeURIComponent(channelName)}`);
      setMessages(data.messages);
      if (scrollToBottom) setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch { /* silent */ }
  }, []);

  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [db, ws, chans, os, bd, act] = await Promise.all([
        fetchWithRetry<OrgDashboard>("/api/org"),
        fetchWithRetry<{ workers: WorkerInfo[] }>("/api/workers"),
        fetchWithRetry<{ channels: Channel[] }>("/api/messages?channel=_channels"),
        fetchWithRetry<{ okrs: OKRInfo[] }>("/api/okrs"),
        fetchWithRetry<{ beads: Bead[]; dependencies: Dependency[] }>("/api/beads"),
        fetchWithRetry<{ activity: ActivityEntry[] }>("/api/activity"),
      ]);
      setDashboard(db);
      setWorkers(ws.workers);
      setChannels(chans.channels);
      setOKRs(os.okrs ?? []);
      setBeads(bd.beads ?? []);
      setBeadDeps(bd.dependencies ?? []);
      setActivity(act.activity);
      setError(null);
      setActiveChannel((prev) => {
        const chan = prev ?? chans.channels[0]?.name ?? null;
        if (chan) fetchMessages(chan, !silent);
        return chan;
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [fetchMessages]);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => {
    const iv = setInterval(() => fetchAll(true), POLL_INTERVAL);
    return () => clearInterval(iv);
  }, [fetchAll]);

  const handleChannelSelect = useCallback((channelName: string) => {
    setActiveChannel(channelName);
    setReplyText("");
    fetchMessages(channelName);
    // Auto-mark all messages in channel as read
    fetch(`/api/messages/read-all?channel=${encodeURIComponent(channelName)}`, { method: "POST" })
      .then(() => setChannels((prev) => prev.map((c) => c.name === channelName ? { ...c, unread_count: 0 } : c)))
      .catch(() => { /* silent */ });
  }, [fetchMessages]);

  const handleWorkerAction = useCallback(async (workerId: string, action: "pause" | "resume" | "fire") => {
    prevWorkersRef.current = workers;
    toast(`${action.charAt(0).toUpperCase() + action.slice(1)}ing…`);
    try {
      await fetchWithRetry(`/api/workers/${workerId}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      toast(`Worker ${action}d`, "success");
      fetchAll(true);
    } catch (err) {
      toast(`Failed: ${err}`, "error");
      setWorkers(prevWorkersRef.current);
    }
  }, [workers, toast, fetchAll]);

  const handleSend = useCallback(async () => {
    if (!replyText.trim() || !activeChannel || sending) return;
    setSending(true);
    const activeChanObj = channels.find((c) => c.name === activeChannel);
    if (!activeChanObj) { setSending(false); return; }

    const optimistic: Message = {
      id: `optimistic-${Date.now()}`,
      from_worker_id: "board-operator",
      from_worker_name: "You",
      channel_name: activeChannel,
      content: replyText,
      priority: 2,
      created_at: new Date().toISOString(),
      is_read: true,
    };
    setMessages((prev) => [...prev, optimistic]);
    const text = replyText;
    setReplyText("");
    setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    try {
      await fetchWithRetry(`/api/channels/${activeChanObj.id}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text }),
      });
      fetchMessages(activeChannel, false);
    } catch (err) {
      toast(`Failed to send: ${err}`, "error");
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
    } finally {
      setSending(false);
    }
  }, [replyText, activeChannel, sending, channels, toast, fetchMessages]);

  const totalUnread = channels.reduce((sum, c) => sum + (c.unread_count ?? 0), 0);

  if (loading) {
    return (
      <div className="board-layout" style={{ justifyContent: "center", alignItems: "center" }}>
        <span className="spinner">⟳</span>&nbsp;Loading…
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
              dashboard.org.status}`}>
              {dashboard.health.overall_score === "critical" ? "⚠ Critical" :
               dashboard.health.overall_score === "warning" ? `⚠ Warning (${dashboard.health.workers_with_issues})` :
               dashboard.org.status}
            </span>
          </>
        )}
        <span style={{ marginLeft: "auto", color: "var(--fg-muted)", fontSize: 12 }}>refreshes every {POLL_INTERVAL / 1000}s</span>
        <button style={{ fontSize: 12, padding: "2px 10px" }} onClick={() => fetchAll(true)}>↺ Refresh</button>
      </header>

      {/* Tab bar */}
      <nav className="tab-bar">
        {TABS.map((t) => (
          <button key={t} className={`tab ${tab === t ? "tab--active" : ""}`} onClick={() => router.push(`/${t}`)}>
            {t === "messages" && totalUnread > 0 ? `Messages (${totalUnread})` :
             t === "okrs" ? `OKRs${okrs.length > 0 ? ` (${okrs.filter((o) => o.status === "active").length})` : ""}` :
             t === "work" ? `Work${beads.length > 0 ? ` (${beads.filter((b) => b.status !== "closed" && b.status !== "deferred").length})` : ""}` :
             t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>

      <main className={tab === "okrs" ? "tab-content--flush" : "tab-content"}>

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
                  <th>Name</th><th>Role</th><th>Team</th><th>Status</th>
                  <th style={{ width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {workers.map((w) => <WorkerRow key={w.id} worker={w} onAction={handleWorkerAction} />)}
                {workers.length === 0 && <tr><td colSpan={6} className="empty-state">No workers found</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {/* ── MESSAGES (Slack-style) ── */}
        {tab === "messages" && (
          <div className="chat-layout" style={{ margin: "-20px" }}>
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
                  <span className="channel-item__icon">{ch.name.startsWith("dm-") ? "◎" : "#"}</span>
                  <span className="channel-item__name">{formatChannelLabel(ch, workers)}</span>
                  {ch.unread_count > 0 && <span className="channel-item__badge">{ch.unread_count}</span>}
                </button>
              ))}
            </div>

            {/* Chat pane */}
            <div className="chat-pane">
              {/* Channel header */}
              {activeChannel && (
                <div className="chat-header">
                  <span className="chat-header__icon">{activeChannel.startsWith("dm-") ? "◎" : "#"}</span>
                  <span className="chat-header__name">
                    {formatChannelLabel(channels.find((c) => c.name === activeChannel) ?? { id: "", name: activeChannel, channel_type: "topic", message_count: 0, unread_count: 0 }, workers)}
                  </span>
                  <span className="chat-header__count">{messages.length} messages</span>
                </div>
              )}

              {/* Messages feed */}
              <div className="chat-feed">
                {messages.length === 0 && (
                  <div className="empty-state" style={{ marginTop: 60 }}>No messages in this channel yet</div>
                )}
                {messages.map((msg, i) => {
                  const isWelcome = msg.content.startsWith(`Welcome ${msg.from_worker_name}!`);
                  if (isWelcome) {
                    return (
                      <div key={msg.id} className="chat-join">
                        <Avatar name={msg.from_worker_name} size={20} />
                        <span className="chat-join__name">{msg.from_worker_name}</span>
                        <span className="chat-join__text">joined the channel</span>
                        <span className="chat-join__time">{formatRelativeTime(msg.created_at)}</span>
                      </div>
                    );
                  }
                  const prev = messages.slice(0, i).reverse().find((m) => !m.content.startsWith(`Welcome ${m.from_worker_name}!`));
                  const isGrouped = prev && prev.from_worker_id === msg.from_worker_id &&
                    (new Date(msg.created_at).getTime() - new Date(prev.created_at).getTime()) < 5 * 60 * 1000;
                  return (
                    <div key={msg.id} className={`chat-msg ${isGrouped ? "chat-msg--grouped" : ""} ${!msg.is_read ? "chat-msg--unread" : ""}`}>
                      {isGrouped ? (
                        <div className="chat-msg__gutter">
                          <span className="chat-msg__hover-time">{new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                        </div>
                      ) : (
                        <div className="chat-msg__gutter">
                          <Avatar name={msg.from_worker_name} size={36} />
                        </div>
                      )}
                      <div className="chat-msg__body">
                        {!isGrouped && (
                          <div className="chat-msg__header">
                            <span className="chat-msg__name">{msg.from_worker_name}</span>
                            <span className="chat-msg__time">{formatRelativeTime(msg.created_at)}</span>
                            {!msg.is_read && <span className="unread-dot" title="unread" />}
                          </div>
                        )}
                        <div className="chat-msg__text">{msg.content}</div>
                      </div>
                    </div>
                  );
                })}
                <div ref={chatBottomRef} />
              </div>

              {/* Compose box */}
              <div className="chat-compose">
                <textarea
                  className="chat-compose__input"
                  placeholder={activeChannel ? `Message #${activeChannel}` : "Select a channel"}
                  value={replyText}
                  disabled={!activeChannel || messages.length === 0}
                  rows={1}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                />
                <button
                  className="chat-compose__send"
                  disabled={!replyText.trim() || sending}
                  onClick={handleSend}
                  title="Send (Enter)"
                >
                  {sending ? "…" : "↑"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── OKRs ── */}
        {tab === "okrs" && <OKRTimeline okrs={okrs} />}

        {/* ── WORK ── */}
        {tab === "work" && <WorkBoard beads={beads} dependencies={beadDeps} />}

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

      <div className="toast-container">
        {toasts.map((t) => <div key={t.id} className={`toast toast--${t.type}`}>{t.message}</div>)}
      </div>
    </div>
  );
}

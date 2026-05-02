"use client";
import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { WorkerRow } from "@/components/WorkerRow";
import { WorkBoard } from "@/components/WorkBoard";
import { OKRTimeline } from "@/components/OKRTimeline";
import { formatCurrency, formatRelativeTime, formatElapsed, formatCurrencyShort } from "@/lib/transforms";
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
  // Directive bar: ':' in Team view → DM a worker
  const [directiveOpen, setDirectiveOpen] = useState(false);
  const [directiveTarget, setDirectiveTarget] = useState<WorkerInfo | null>(null);
  const [directiveText, setDirectiveText] = useState("");
  const [directiveQuery, setDirectiveQuery] = useState("");
  // ⌘K command palette
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [paletteIdx, setPaletteIdx] = useState(0);
  // Activity filter
  const [activityFilter, setActivityFilter] = useState<string>("all");
  // Team keyboard nav
  const [teamFocusIdx, setTeamFocusIdx] = useState<number>(-1);
  const [teamFilter, setTeamFilter] = useState<string>("");
  // Worker detail panel
  const [selectedWorker, setSelectedWorker] = useState<WorkerInfo | null>(null);
  const [workerBeads, setWorkerBeads] = useState<{ in_progress: unknown[]; open: unknown[] } | null>(null);
  // Global search results in palette
  const [searchResults, setSearchResults] = useState<Array<{ type: string; id: string; title: string; subtitle: string; tab: string }>>([]);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const directiveInputRef = useRef<HTMLInputElement>(null);
  const directiveMsgRef = useRef<HTMLTextAreaElement>(null);
  const paletteInputRef = useRef<HTMLInputElement>(null);
  const toastIdRef = useRef(0);
  const prevWorkersRef = useRef<WorkerInfo[]>([]);
  const sseRef = useRef<EventSource | null>(null);

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

  // SSE for active channel — real-time message push, falls back to polling
  useEffect(() => {
    if (!activeChannel) return;
    sseRef.current?.close();
    const es = new EventSource(`/api/messages/stream?channel=${encodeURIComponent(activeChannel)}`);
    sseRef.current = es;
    es.addEventListener("messages", (e) => {
      const { messages: newMsgs } = JSON.parse(e.data) as { messages: Message[] };
      if (newMsgs.length > 0) {
        setMessages((prev) => {
          const ids = new Set(prev.map((m) => m.id));
          const added = newMsgs.filter((m) => !ids.has(m.id));
          if (!added.length) return prev;
          setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
          return [...prev, ...added];
        });
      }
    });
    es.onerror = () => es.close();
    return () => { es.close(); sseRef.current = null; };
  }, [activeChannel]);

  // Slower polling for everything else (workers, okrs, beads, activity, channel list)
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

  const filteredWorkers = useMemo(() =>
    !teamFilter ? workers : workers.filter((w) => w.name.toLowerCase().includes(teamFilter.toLowerCase()) || w.role.toLowerCase().includes(teamFilter.toLowerCase())),
    [workers, teamFilter]
  );

  // Broadcast @all: send directive to every worker
  const handleBroadcast = useCallback(async (text: string) => {
    if (!text.trim() || sending) return;
    setSending(true);
    let sent = 0;
    for (const w of workers) {
      try {
        const dmRes = await fetchWithRetry<{ channel: string }>("/api/channels/dm", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ worker_id: w.id }),
        });
        const chanId = typeof dmRes.channel === "object" ? (dmRes.channel as { id: string }).id : dmRes.channel;
        await fetchWithRetry(`/api/channels/${chanId}/messages`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: text.trim() }),
        });
        sent++;
      } catch { /* continue */ }
    }
    toast(`Broadcast sent to ${sent}/${workers.length} workers`);
    setSending(false);
    setDirectiveOpen(false);
    setDirectiveText("");
    setDirectiveTarget(null);
  }, [workers, sending, toast]);

  // Send a DM to a worker from the directive bar
  const handleDirectiveSend = useCallback(async () => {
    if (!directiveText.trim() || !directiveTarget) return;
    if (directiveTarget.id === "@all") { await handleBroadcast(directiveText); return; }
    setSending(true);
    try {
      const dmRes = await fetchWithRetry<{ channel: string }>("/api/channels/dm", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ worker_id: directiveTarget.id }),
      });
      const chanId = typeof dmRes.channel === "object" ? (dmRes.channel as { id: string }).id : dmRes.channel;
      await fetchWithRetry(`/api/channels/${chanId}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: directiveText.trim() }),
      });
      toast(`Directive sent to ${directiveTarget.name}`);
      setDirectiveOpen(false);
      setDirectiveText("");
      setDirectiveTarget(null);
      setDirectiveQuery("");
    } catch (err) {
      toast(`Failed: ${err}`, "error");
    } finally {
      setSending(false);
    }
  }, [directiveText, directiveTarget, toast, handleBroadcast]);

  // Debounced global search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (!paletteQuery || paletteQuery.length < 2) { setSearchResults([]); return; }
    searchTimerRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(paletteQuery)}`);
        const data = await res.json() as { results: Array<{ type: string; id: string; title: string; subtitle: string; tab: string }> };
        setSearchResults(data.results ?? []);
      } catch { setSearchResults([]); }
    }, 200);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [paletteQuery]);

  const SLASH_COMMANDS = [
    { cmd: "/loop", desc: "Start autonomous work loop" },
    { cmd: "/ultrareview", desc: "Multi-agent cloud code review" },
    { cmd: "/feature-lifecycle", desc: "TDD-driven feature planning" },
    { cmd: "/reality-check", desc: "Verify claims with evidence" },
    { cmd: "/fast", desc: "Toggle fast mode (Opus 4.6)" },
    { cmd: "/clear", desc: "Clear conversation context" },
  ];

  // ⌘K palette items — search results take priority when query is 2+ chars
  const paletteItems = useMemo(() => {
    const q = paletteQuery.toLowerCase();
    const items: Array<{ label: string; sub?: string; icon?: string; action: () => void }> = [];

    // Global search results (messages, workers, OKRs)
    if (searchResults.length > 0) {
      const icons: Record<string, string> = { message: "#", worker: "@", okr: "◎" };
      searchResults.forEach((r) => {
        items.push({
          label: r.title,
          sub: r.subtitle,
          icon: icons[r.type] ?? "·",
          action: () => { router.push(`/${r.tab}`); setPaletteOpen(false); },
        });
      });
      return items.slice(0, 9);
    }

    // Default items when no search query
    // Tab jumps
    TABS.forEach((t) => {
      if (!q || t.includes(q)) items.push({ label: `Go to ${t.charAt(0).toUpperCase() + t.slice(1)}`, sub: "tab", action: () => { router.push(`/${t}`); setPaletteOpen(false); } });
    });
    // Broadcast
    if (!q || "broadcast all workers".includes(q)) {
      items.push({ label: "Broadcast to all workers", sub: "@all", action: () => { setDirectiveTarget(null); setDirectiveQuery("@all"); setDirectiveOpen(true); setPaletteOpen(false); setTimeout(() => directiveInputRef.current?.focus(), 50); } });
    }
    // Workers
    workers.filter((w) => !q || w.name.toLowerCase().includes(q) || w.role.toLowerCase().includes(q)).forEach((w) => {
      items.push({ label: `DM ${w.name}`, sub: w.role, action: () => { setDirectiveTarget(w); setDirectiveText(""); setDirectiveOpen(true); setPaletteOpen(false); setTimeout(() => directiveMsgRef.current?.focus(), 50); } });
    });
    // Slash commands
    SLASH_COMMANDS.filter(({ cmd, desc }) => !q || cmd.includes(q) || desc.toLowerCase().includes(q)).forEach(({ cmd, desc }) => {
      items.push({ label: cmd, sub: desc, action: () => { navigator.clipboard?.writeText(cmd).catch(() => {}); toast(`Copied ${cmd}`); setPaletteOpen(false); } });
    });
    return items.slice(0, 9);
  }, [paletteQuery, searchResults, workers, router, toast]);

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // ⌘K / Ctrl+K → palette
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        setPaletteQuery("");
        setPaletteIdx(0);
        setTimeout(() => paletteInputRef.current?.focus(), 50);
        return;
      }
      const inInput = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement;
      // ':' in team tab → directive bar
      if (e.key === ":" && tab === "team" && !directiveOpen && !paletteOpen && !inInput) {
        e.preventDefault();
        const target = teamFocusIdx >= 0 ? filteredWorkers[teamFocusIdx] ?? null : null;
        setDirectiveOpen(true);
        setDirectiveTarget(target);
        setDirectiveText("");
        setDirectiveQuery("");
        setTimeout(() => (target ? directiveMsgRef.current : directiveInputRef.current)?.focus(), 50);
        return;
      }
      // j/k vim nav in team tab
      if (tab === "team" && !directiveOpen && !paletteOpen && !inInput) {
        if (e.key === "j") { e.preventDefault(); setTeamFocusIdx((i) => Math.min(i + 1, filteredWorkers.length - 1)); return; }
        if (e.key === "k") { e.preventDefault(); setTeamFocusIdx((i) => Math.max(i - 1, 0)); return; }
        if (e.key === "Enter" && teamFocusIdx >= 0) {
          e.preventDefault();
          const w = filteredWorkers[teamFocusIdx];
          if (w) { setDirectiveTarget(w); setDirectiveText(""); setDirectiveOpen(true); setTimeout(() => directiveMsgRef.current?.focus(), 50); }
          return;
        }
        if (e.key === "/" ) { e.preventDefault(); /* focus handled by filter input rendered in team tab */ return; }
      }
      if (e.key === "Escape") {
        setPaletteOpen(false);
        setDirectiveOpen(false);
        setTeamFilter("");
        setTeamFocusIdx(-1);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [tab, directiveOpen, paletteOpen]);

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
        <button style={{ fontSize: 12, padding: "2px 10px" }} title="Command palette (⌘K)" onClick={() => { setPaletteOpen(true); setTimeout(() => paletteInputRef.current?.focus(), 50); }}>⌘K</button>
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
                {dashboard.health.issues.map((issue, i) => {
                  const fixAction = issue.issue_type === "no_okrs"
                    ? { label: "Tell worker to set OKRs →", handler: () => {
                        const w = workers.find((x) => x.id === issue.worker_id);
                        if (w) { setDirectiveTarget(w); setDirectiveText("Please create an OKR for your role with at least one measurable key result using: qn org okr set"); setDirectiveOpen(true); router.push("/team"); }
                      }}
                    : issue.issue_type === "no_session"
                    ? { label: "Resume session →", handler: () => handleWorkerAction(issue.worker_id ?? "", "resume") }
                    : null;
                  return (
                    <div key={i} className={`health-issue health-issue--${issue.severity}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div>
                        <span className="health-issue__icon">{issue.severity === "error" ? "●" : "○"}</span>
                        <span className="health-issue__message">{issue.message}</span>
                      </div>
                      {fixAction && (
                        <button
                          style={{ fontSize: 11, padding: "2px 8px", marginLeft: 12, whiteSpace: "nowrap", opacity: 0.85 }}
                          onClick={fixAction.handler}
                        >
                          {fixAction.label}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {/* Spend by worker mini-chart */}
            {workers.filter((w) => w.spend_used > 0).length > 0 && (
              <div style={{ marginTop: 20 }}>
                <div className="section-title" style={{ marginBottom: 10 }}>Spend by worker</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {[...workers].sort((a, b) => b.spend_used - a.spend_used).filter((w) => w.spend_used > 0 || w.spend_allocated > 0).slice(0, 8).map((w) => {
                    const maxSpend = Math.max(...workers.map((x) => x.spend_allocated || x.spend_used || 1));
                    const pct = maxSpend > 0 ? Math.min(100, (w.spend_used / maxSpend) * 100) : 0;
                    const allocPct = maxSpend > 0 ? Math.min(100, (w.spend_allocated / maxSpend) * 100) : 0;
                    return (
                      <div key={w.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ minWidth: 60, fontSize: 12, color: "var(--fg-muted)", textAlign: "right" }}>{w.name}</span>
                        <div style={{ flex: 1, height: 14, background: "var(--bg-3)", borderRadius: 3, position: "relative", overflow: "hidden" }}>
                          {allocPct > 0 && <div style={{ position: "absolute", inset: 0, width: `${allocPct}%`, background: "rgba(88,166,255,0.1)", borderRight: "1px dashed rgba(88,166,255,0.3)" }} />}
                          <div style={{ position: "absolute", inset: 0, width: `${pct}%`, background: w.spend_used / (w.spend_allocated || 1) > 0.8 ? "var(--red)" : "#3fb950", borderRadius: 3 }} />
                        </div>
                        <span style={{ fontSize: 11, color: "var(--fg-muted)", minWidth: 70, textAlign: "right" }}>
                          {formatCurrencyShort(w.spend_used)} / {formatCurrencyShort(w.spend_allocated)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {dashboard.org.started_at && (
              <div style={{ color: "var(--fg-muted)", fontSize: 12, marginTop: 12 }}>
                Started {formatRelativeTime(dashboard.org.started_at)}
                {dashboard.org.ceo_worker_id && ` · CEO: ${workers.find((w) => w.id === dashboard.org.ceo_worker_id)?.name ?? dashboard.org.ceo_worker_id}`}
              </div>
            )}
          </div>
        )}

        {/* ── TEAM ── */}
        {tab === "team" && (
          <div>
            <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 10 }}>
              <input
                placeholder="/ filter workers…"
                value={teamFilter}
                onChange={(e) => { setTeamFilter(e.target.value); setTeamFocusIdx(-1); }}
                onKeyDown={(e) => { if (e.key === "Escape") { setTeamFilter(""); setTeamFocusIdx(-1); } }}
                style={{ fontSize: 12, padding: "4px 10px", background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--fg)", outline: "none", width: 180 }}
              />
              <span style={{ fontSize: 12, color: "var(--fg-muted)" }}>
                {filteredWorkers.length} workers · <kbd style={{ background: "var(--bg-3)", padding: "1px 4px", borderRadius: 3, fontSize: 11 }}>j/k</kbd> navigate · <kbd style={{ background: "var(--bg-3)", padding: "1px 4px", borderRadius: 3, fontSize: 11 }}>:</kbd> directive
              </span>
            </div>
            <table className="workers-table">
              <thead>
                <tr>
                  <th style={{ width: 16 }}></th>
                  <th style={{ width: 16 }}></th>
                  <th>Name</th><th>Role</th><th>Team</th><th>Status</th><th>Session</th>
                  <th style={{ width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {filteredWorkers.map((w, i) => {
                  const elapsed = w.session_started_at ? formatElapsed(w.session_started_at) : "";
                  const cost = w.spend_used > 0 ? formatCurrencyShort(w.spend_used) : "";
                  const stale = w.last_activity
                    ? (Date.now() - new Date(w.last_activity).getTime()) / 60000
                    : null;
                  const staleStr = stale !== null && stale > 30
                    ? `idle ${stale > 120 ? `${Math.round(stale / 60)}h` : `${Math.round(stale)}m`}`
                    : null;
                  const sessionInfo = [elapsed, cost, staleStr].filter(Boolean).join(" · ");
                  const isFocused = teamFocusIdx === i;
                  const isSelected = selectedWorker?.id === w.id;
                  return (
                    <WorkerRow
                      key={w.id}
                      worker={w}
                      onAction={handleWorkerAction}
                      onClick={() => {
                        setTeamFocusIdx(i);
                        if (isSelected) { setSelectedWorker(null); setWorkerBeads(null); return; }
                        setSelectedWorker(w);
                        setWorkerBeads(null);
                        fetch(`/api/workers/${w.id}/beads`)
                          .then((r) => r.json())
                          .then((d) => setWorkerBeads(d))
                          .catch(() => {});
                      }}
                      focused={isFocused || isSelected}
                      sessionInfo={sessionInfo}
                    />
                  );
                })}
                {filteredWorkers.length === 0 && <tr><td colSpan={8} className="empty-state">No workers match "{teamFilter}"</td></tr>}
              </tbody>
            </table>

            {/* Worker detail panel */}
            {selectedWorker && (
              <div style={{ marginTop: 16, background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "14px 16px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                  <Avatar name={selectedWorker.name} size={28} />
                  <div>
                    <span style={{ fontWeight: 600 }}>{selectedWorker.name}</span>
                    <span style={{ color: "var(--fg-muted)", fontSize: 12, marginLeft: 8 }}>{selectedWorker.role}</span>
                  </div>
                  <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                    <button style={{ fontSize: 11, padding: "3px 10px" }} onClick={() => { setDirectiveTarget(selectedWorker); setDirectiveText(""); setDirectiveOpen(true); setTimeout(() => directiveMsgRef.current?.focus(), 50); }}>
                      Send directive
                    </button>
                    <button style={{ fontSize: 11, padding: "3px 10px" }} onClick={() => { setSelectedWorker(null); setWorkerBeads(null); }}>✕</button>
                  </div>
                </div>
                {selectedWorker.last_activity && (
                  <div style={{ fontSize: 12, color: "var(--fg-muted)", marginBottom: 10 }}>
                    Last activity: {formatRelativeTime(selectedWorker.last_activity)}
                    {selectedWorker.session_started_at && ` · Session running ${formatElapsed(selectedWorker.session_started_at)}`}
                    {selectedWorker.spend_used > 0 && ` · ${formatCurrencyShort(selectedWorker.spend_used)} spent`}
                  </div>
                )}
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--fg-muted)" }}>Active work</div>
                {!workerBeads ? (
                  <div style={{ fontSize: 12, color: "var(--fg-muted)" }}>Loading beads…</div>
                ) : (workerBeads.in_progress as Array<{ id: string; title: string; status: string; updated_at?: string }>).length === 0 && (workerBeads.open as unknown[]).length === 0 ? (
                  <div style={{ fontSize: 12, color: "var(--fg-muted)" }}>No open beads assigned</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {(workerBeads.in_progress as Array<{ id: string; title: string; status: string; updated_at?: string }>).map((b) => (
                      <div key={b.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "rgba(35,134,54,0.1)", border: "1px solid rgba(35,134,54,0.3)", borderRadius: 6 }}>
                        <span style={{ fontSize: 10, background: "#238636", color: "#fff", padding: "1px 5px", borderRadius: 3 }}>IN PROGRESS</span>
                        <span style={{ fontSize: 13, flex: 1 }}>{b.title}</span>
                        <span style={{ fontSize: 11, color: "var(--fg-muted)" }}>{b.id}</span>
                        {b.updated_at && <span style={{ fontSize: 11, color: "var(--fg-muted)" }}>{formatRelativeTime(b.updated_at)}</span>}
                      </div>
                    ))}
                    {(workerBeads.open as Array<{ id: string; title: string }>).slice(0, 3).map((b) => (
                      <div key={b.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 10px", background: "var(--bg-3)", borderRadius: 6 }}>
                        <span style={{ fontSize: 10, color: "var(--fg-muted)", minWidth: 28 }}>open</span>
                        <span style={{ fontSize: 12, flex: 1, color: "var(--fg-muted)" }}>{b.title}</span>
                        <span style={{ fontSize: 11, color: "var(--fg-muted)" }}>{b.id}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
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
        {tab === "okrs" && (
          <OKRTimeline
            okrs={okrs}
            onKrUpdate={(okrId, metric, current) => {
              setOKRs((prev) => prev.map((o) =>
                o.id !== okrId ? o : {
                  ...o,
                  key_results: o.key_results.map((kr) =>
                    kr.metric === metric ? { ...kr, current } : kr
                  ),
                }
              ));
            }}
          />
        )}

        {/* ── WORK ── */}
        {tab === "work" && <WorkBoard beads={beads} dependencies={beadDeps} />}

        {/* ── ACTIVITY ── */}
        {tab === "activity" && (
          <div>
            <div className="section-title" style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12 }}>
              Recent activity
              <select
                value={activityFilter}
                onChange={(e) => setActivityFilter(e.target.value)}
                style={{ fontSize: 12, padding: "2px 6px", background: "var(--bg-2)", color: "var(--fg)", border: "1px solid var(--border)", borderRadius: 4 }}
              >
                <option value="all">All workers</option>
                {workers.map((w) => <option key={w.id} value={w.name}>{w.name}</option>)}
              </select>
            </div>
            {activity.length === 0 && <div className="empty-state">No recent activity</div>}
            <div className="activity-list">
              {activity
                .filter((e) => activityFilter === "all" || e.worker_name === activityFilter)
                .map((entry, i) => (
                  <div key={i} className="activity-item">
                    <span className="activity-item__time">{formatRelativeTime(entry.timestamp)}</span>
                    <span className="activity-item__worker">{entry.worker_name}</span>
                    <span className="activity-item__summary">{entry.summary}</span>
                  </div>
                ))}
              {activity.filter((e) => activityFilter === "all" || e.worker_name === activityFilter).length === 0 && (
                <div className="empty-state">No activity for {activityFilter}</div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* ── DIRECTIVE BAR ── */}
      {directiveOpen && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 200,
          display: "flex", alignItems: "flex-end", justifyContent: "center", padding: "0 0 80px",
        }} onClick={() => setDirectiveOpen(false)}>
          <div style={{
            background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 10,
            padding: 20, width: "min(560px, 90vw)", boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ fontSize: 12, color: "var(--fg-muted)", marginBottom: 10 }}>
              Send directive to worker
            </div>
            {/* Worker selector */}
            {!directiveTarget ? (
              <>
                <input
                  ref={directiveInputRef}
                  placeholder="Search worker…"
                  value={directiveQuery}
                  onChange={(e) => setDirectiveQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Escape" && setDirectiveOpen(false)}
                  style={{ width: "100%", padding: "8px 12px", fontSize: 14, background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--fg)", outline: "none", boxSizing: "border-box" }}
                />
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                  {/* @all broadcast option */}
                  {(!directiveQuery || "@all".includes(directiveQuery.toLowerCase()) || "all workers".includes(directiveQuery.toLowerCase())) && (
                    <button style={{ textAlign: "left", padding: "6px 10px", background: "var(--bg-3)", border: "1px solid #d29922", borderRadius: 6, color: "var(--fg)", cursor: "pointer", fontSize: 13 }}
                      onClick={() => { setDirectiveTarget({ id: "@all", name: "All Workers", role: "broadcast" } as unknown as WorkerInfo); setTimeout(() => directiveMsgRef.current?.focus(), 30); }}>
                      <strong>@all</strong> <span style={{ color: "#d29922", fontSize: 11 }}>Broadcast to {workers.length} workers</span>
                    </button>
                  )}
                  {workers
                    .filter((w) => !directiveQuery || w.name.toLowerCase().includes(directiveQuery.toLowerCase()) || w.role.toLowerCase().includes(directiveQuery.toLowerCase()))
                    .slice(0, 5)
                    .map((w) => (
                      <button key={w.id} style={{ textAlign: "left", padding: "6px 10px", background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--fg)", cursor: "pointer", fontSize: 13 }}
                        onClick={() => { setDirectiveTarget(w); setTimeout(() => directiveMsgRef.current?.focus(), 30); }}>
                        <strong>{w.name}</strong> <span style={{ color: "var(--fg-muted)", fontSize: 11 }}>{w.role}</span>
                      </button>
                    ))}
                </div>
              </>
            ) : (
              <>
                <div style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
                  {directiveTarget.id === "@all"
                    ? <span style={{ fontSize: 18 }}>📢</span>
                    : <Avatar name={directiveTarget.name} size={24} />}
                  <span style={{ fontWeight: 600 }}>{directiveTarget.name}</span>
                  {directiveTarget.id === "@all"
                    ? <span style={{ color: "#d29922", fontSize: 12 }}>→ {workers.length} workers via DM</span>
                    : <span style={{ color: "var(--fg-muted)", fontSize: 12 }}>{directiveTarget.role}</span>}
                  <button style={{ marginLeft: "auto", fontSize: 11, padding: "2px 8px" }} onClick={() => setDirectiveTarget(null)}>change</button>
                </div>
                <textarea
                  ref={directiveMsgRef}
                  placeholder={directiveTarget.id === "@all" ? "Message to all workers…" : `Message to ${directiveTarget.name}…`}
                  value={directiveText}
                  rows={3}
                  onChange={(e) => setDirectiveText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleDirectiveSend(); }
                    if (e.key === "Escape") setDirectiveOpen(false);
                  }}
                  style={{ width: "100%", padding: "8px 12px", fontSize: 14, background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--fg)", outline: "none", resize: "none", boxSizing: "border-box", fontFamily: "inherit" }}
                />
                <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end", gap: 8 }}>
                  <button onClick={() => setDirectiveOpen(false)}>Cancel</button>
                  <button className="primary" disabled={!directiveText.trim() || sending} onClick={handleDirectiveSend}>
                    {sending ? "Sending…" : "Send ↑"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── ⌘K PALETTE ── */}
      {paletteOpen && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 200,
          display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: 120,
        }} onClick={() => setPaletteOpen(false)}>
          <div style={{
            background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 10,
            width: "min(520px, 90vw)", boxShadow: "0 8px 40px rgba(0,0,0,0.5)", overflow: "hidden",
          }} onClick={(e) => e.stopPropagation()}>
            <input
              ref={paletteInputRef}
              placeholder="Search messages, workers, OKRs — or jump to tab…"
              value={paletteQuery}
              onChange={(e) => { setPaletteQuery(e.target.value); setPaletteIdx(0); }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") { e.preventDefault(); setPaletteIdx((i) => Math.min(i + 1, paletteItems.length - 1)); }
                if (e.key === "ArrowUp") { e.preventDefault(); setPaletteIdx((i) => Math.max(i - 1, 0)); }
                if (e.key === "Enter" && paletteItems[paletteIdx]) { paletteItems[paletteIdx].action(); }
                if (e.key === "Escape") setPaletteOpen(false);
              }}
              style={{ width: "100%", padding: "14px 16px", fontSize: 15, background: "transparent", border: "none", borderBottom: "1px solid var(--border)", color: "var(--fg)", outline: "none", boxSizing: "border-box" }}
            />
            <div>
              {paletteItems.map((item, i) => (
                <div key={i} onClick={item.action} style={{
                  padding: "9px 16px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center",
                  background: i === paletteIdx ? "var(--bg-3)" : "transparent",
                  borderLeft: i === paletteIdx ? "2px solid var(--accent)" : "2px solid transparent",
                }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
                    {item.icon && <span style={{ color: "var(--fg-muted)", fontSize: 12, minWidth: 12 }}>{item.icon}</span>}
                    {item.label}
                  </span>
                  {item.sub && <span style={{ fontSize: 11, color: "var(--fg-muted)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.sub}</span>}
                </div>
              ))}
              {paletteItems.length === 0 && (
                <div style={{ padding: "16px", color: "var(--fg-muted)", fontSize: 13 }}>No results</div>
              )}
            </div>
            <div style={{ padding: "6px 12px", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--fg-muted)", display: "flex", gap: 12 }}>
              <span>↑↓ navigate</span><span>↵ select</span><span>Esc close</span>
            </div>
          </div>
        </div>
      )}

      <div className="toast-container">
        {toasts.map((t) => <div key={t.id} className={`toast toast--${t.type}`}>{t.message}</div>)}
      </div>
    </div>
  );
}

"use client";
import { useMemo, useRef, useEffect, useState } from "react";
import type { OKRInfo, KeyResult } from "@/lib/types";

interface Props {
  okrs: OKRInfo[];
  onKrUpdate?: (okrId: string, metric: string, current: number) => void;
}

const ROW_H = 48;
const SIDEBAR_W = 280;
const BAR_H = 22;
const BAR_Y_OFFSET = (ROW_H - BAR_H) / 2;
const MIN_RANGE_DAYS = 90;

const STATUS_COLORS: Record<string, string> = {
  active:    "#238636",
  draft:     "#1f6feb",
  completed: "#6e7681",
  cancelled: "#b91c1c",
};
const STATUS_FILL: Record<string, string> = {
  active:    "rgba(35,134,54,0.25)",
  draft:     "rgba(31,111,235,0.15)",
  completed: "rgba(110,118,129,0.2)",
  cancelled: "rgba(185,28,28,0.2)",
};

function overallPct(krs: KeyResult[]): number {
  if (!krs.length) return 0;
  return Math.round(krs.reduce((s, kr) => {
    if (kr.unit === "bool") return s + (kr.current >= 1 ? 100 : 0);
    return s + (kr.target > 0 ? Math.min(100, (kr.current / kr.target) * 100) : 0);
  }, 0) / krs.length);
}

function toDate(s: string | null, fallback: Date): Date {
  if (!s) return fallback;
  const d = new Date(s);
  return isNaN(d.getTime()) ? fallback : d;
}

function monthLabel(d: Date) {
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

interface OKRRow extends OKRInfo {
  depth: number;
  start: Date;
  end: Date;
  pct: number;
}

function buildRows(okrs: OKRInfo[], now: Date): OKRRow[] {
  const map = new Map(okrs.map((o) => [o.id, o]));
  const defaultEnd = new Date(now.getFullYear(), now.getMonth() + 3, 0); // end of 3 months out

  function depth(id: string, visited = new Set<string>()): number {
    if (visited.has(id)) return 0;
    visited.add(id);
    const okr = map.get(id);
    if (!okr?.parent_id) return 0;
    return 1 + depth(okr.parent_id, visited);
  }

  // topological sort: roots first, then children
  const roots = okrs.filter((o) => !o.parent_id);
  const ordered: OKRInfo[] = [];
  function visit(o: OKRInfo) {
    ordered.push(o);
    okrs.filter((c) => c.parent_id === o.id).forEach(visit);
  }
  roots.forEach(visit);
  // any orphaned children
  okrs.filter((o) => o.parent_id && !map.has(o.parent_id)).forEach((o) => ordered.push(o));

  return ordered.map((o) => ({
    ...o,
    depth: depth(o.id),
    start: toDate(o.parent_id ? (map.get(o.parent_id)?.due_date ?? null) : null, toDate(null, new Date(o.created_at ?? now.toISOString()))),
    end: toDate(o.due_date, defaultEnd),
    pct: overallPct(o.key_results),
  }));
}

export function OKRTimeline({ okrs, onKrUpdate }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const now = useMemo(() => new Date(), []);
  const [editingKr, setEditingKr] = useState<{ okrId: string; metric: string; current: number } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  const rows = useMemo(() => buildRows(okrs, now), [okrs, now]);

  const handleKrSave = async () => {
    if (!editingKr) return;
    const val = parseFloat(editValue);
    if (isNaN(val)) return;
    setSaving(true);
    try {
      await fetch(`/api/okrs/${editingKr.okrId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: editingKr.metric, current: val }),
      });
      onKrUpdate?.(editingKr.okrId, editingKr.metric, val);
      setEditingKr(null);
    } catch {
      // silent — user can retry
    } finally {
      setSaving(false);
    }
  };

  const { rangeStart, rangeEnd, totalDays } = useMemo(() => {
    if (!rows.length) {
      const s = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const e = new Date(now.getFullYear(), now.getMonth() + 4, 0);
      return { rangeStart: s, rangeEnd: e, totalDays: Math.ceil((e.getTime() - s.getTime()) / 86400000) };
    }
    const starts = rows.map((r) => r.start.getTime());
    const ends = rows.map((r) => r.end.getTime());
    let s = new Date(Math.min(...starts));
    let e = new Date(Math.max(...ends));
    // pad
    s = new Date(s.getFullYear(), s.getMonth() - 1, 1);
    e = new Date(e.getFullYear(), e.getMonth() + 2, 0);
    const days = Math.max(MIN_RANGE_DAYS, Math.ceil((e.getTime() - s.getTime()) / 86400000));
    return { rangeStart: s, rangeEnd: e, totalDays: days };
  }, [rows, now]);

  // Build month markers
  const months = useMemo(() => {
    const result: Array<{ label: string; x: number; width: number }> = [];
    let cursor = new Date(rangeStart.getFullYear(), rangeStart.getMonth(), 1);
    while (cursor < rangeEnd) {
      const next = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
      const x = ((cursor.getTime() - rangeStart.getTime()) / 86400000 / totalDays) * 100;
      const endClamped = next > rangeEnd ? rangeEnd : next;
      const w = ((endClamped.getTime() - cursor.getTime()) / 86400000 / totalDays) * 100;
      result.push({ label: monthLabel(cursor), x, width: w });
      cursor = next;
    }
    return result;
  }, [rangeStart, rangeEnd, totalDays]);

  const todayX = useMemo(
    () => ((now.getTime() - rangeStart.getTime()) / 86400000 / totalDays) * 100,
    [now, rangeStart, totalDays]
  );

  function barX(start: Date) {
    return Math.max(0, ((start.getTime() - rangeStart.getTime()) / 86400000 / totalDays) * 100);
  }
  function barW(start: Date, end: Date) {
    const raw = ((end.getTime() - start.getTime()) / 86400000 / totalDays) * 100;
    return Math.max(0.5, raw);
  }

  const [selectedOkr, setSelectedOkr] = useState<OKRRow | null>(null);

  if (!okrs.length) {
    return <div className="empty-state" style={{ paddingTop: 60 }}>No OKRs yet</div>;
  }

  const totalH = rows.length * ROW_H;

  return (
    <div className="okr-timeline" ref={containerRef}>
      <div className="okr-timeline__inner">
        {/* Sidebar */}
        <div className="okr-timeline__sidebar" style={{ width: SIDEBAR_W }}>
          <div className="okr-timeline__header-cell">Objective</div>
          {rows.map((row) => (
            <div
              key={row.id}
              className="okr-timeline__sidebar-row"
              style={{ height: ROW_H, paddingLeft: 12 + row.depth * 20 }}
            >
              <span
                className="okr-timeline__status-dot"
                style={{ background: STATUS_COLORS[row.status] ?? "#8b949e" }}
              />
              <div className="okr-timeline__row-info">
                <span className="okr-timeline__row-title">{row.title}</span>
                <span className="okr-timeline__row-owner">{row.owner_name}</span>
              </div>
              {row.pct > 0 && (
                <span className="okr-timeline__row-pct" style={{ color: STATUS_COLORS[row.status] }}>
                  {row.pct}%
                </span>
              )}
            </div>
          ))}
        </div>

        {/* Chart area */}
        <div className="okr-timeline__chart">
          {/* Month header */}
          <div className="okr-timeline__header-cell okr-timeline__chart-header">
            {months.map((m) => (
              <div
                key={m.label}
                className="okr-timeline__month"
                style={{ left: `${m.x}%`, width: `${m.width}%` }}
              >
                {m.label}
              </div>
            ))}
          </div>

          {/* Grid + bars */}
          <div className="okr-timeline__canvas" style={{ height: totalH }}>
            {/* Month grid lines */}
            {months.map((m) => (
              <div
                key={m.label}
                className="okr-timeline__grid-line"
                style={{ left: `${m.x}%` }}
              />
            ))}

            {/* Today line */}
            {todayX >= 0 && todayX <= 100 && (
              <div className="okr-timeline__today" style={{ left: `${todayX}%` }}>
                <div className="okr-timeline__today-label">Today</div>
              </div>
            )}

            {/* Row backgrounds */}
            {rows.map((row, i) => (
              <div
                key={row.id}
                className="okr-timeline__row-bg"
                style={{ top: i * ROW_H, height: ROW_H }}
              />
            ))}

            {/* Bars */}
            {rows.map((row, i) => {
              const x = barX(row.start);
              const w = barW(row.start, row.end);
              const isOverdue = row.end < now && row.status === "active";
              return (
                <div
                  key={row.id}
                  className="okr-timeline__bar-wrap"
                  style={{ top: i * ROW_H + BAR_Y_OFFSET, height: BAR_H, left: `${x}%`, width: `${w}%`, cursor: "pointer" }}
                  onClick={() => setSelectedOkr(selectedOkr?.id === row.id ? null : row)}
                >
                  {/* Background track */}
                  <div
                    className="okr-timeline__bar-track"
                    style={{
                      background: STATUS_FILL[row.status] ?? "rgba(139,148,158,0.15)",
                      border: `1px solid ${isOverdue ? "#f85149" : (STATUS_COLORS[row.status] ?? "#8b949e")}`,
                    }}
                  />
                  {/* Progress fill */}
                  {row.pct > 0 && (
                    <div
                      className="okr-timeline__bar-fill"
                      style={{
                        width: `${row.pct}%`,
                        background: STATUS_COLORS[row.status] ?? "#8b949e",
                      }}
                    />
                  )}
                  {/* Label inside bar */}
                  <div className="okr-timeline__bar-label">
                    {row.key_results.length > 0 && (
                      <span>{row.key_results.map((kr) => kr.metric).join(" · ")}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* KR detail panel */}
      {selectedOkr && (
        <div style={{ margin: "12px 0 0", background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "14px 16px" }}>
          <div style={{ fontWeight: 600, marginBottom: 10, display: "flex", justifyContent: "space-between" }}>
            <span>{selectedOkr.title}</span>
            <button style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => setSelectedOkr(null)}>✕</button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {selectedOkr.key_results.map((kr) => {
              const pct = kr.target > 0 ? Math.min(100, Math.round((kr.current / kr.target) * 100)) : 0;
              const isEditing = editingKr?.okrId === selectedOkr.id && editingKr.metric === kr.metric;
              return (
                <div key={kr.metric} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ minWidth: 160, fontSize: 13, color: "var(--fg-muted)" }}>{kr.metric}</span>
                  <div style={{ flex: 1, height: 6, background: "var(--bg-3)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: STATUS_COLORS[selectedOkr.status] ?? "#8b949e", borderRadius: 3 }} />
                  </div>
                  {isEditing ? (
                    <>
                      <input
                        type="number"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") handleKrSave(); if (e.key === "Escape") setEditingKr(null); }}
                        autoFocus
                        style={{ width: 70, padding: "2px 6px", fontSize: 12, background: "var(--bg-3)", border: "1px solid var(--accent)", borderRadius: 4, color: "var(--fg)" }}
                      />
                      <span style={{ fontSize: 11, color: "var(--fg-muted)" }}>/ {kr.target} {kr.unit}</span>
                      <button style={{ fontSize: 11, padding: "2px 6px" }} disabled={saving} onClick={handleKrSave}>{saving ? "…" : "✓"}</button>
                      <button style={{ fontSize: 11, padding: "2px 6px" }} onClick={() => setEditingKr(null)}>✕</button>
                    </>
                  ) : (
                    <>
                      <span style={{ fontSize: 12, minWidth: 80 }}>{kr.current} / {kr.target} {kr.unit}</span>
                      <button
                        style={{ fontSize: 11, padding: "2px 6px", opacity: 0.7 }}
                        title="Update current value"
                        onClick={() => { setEditingKr({ okrId: selectedOkr.id, metric: kr.metric, current: kr.current }); setEditValue(String(kr.current)); }}
                      >edit</button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* KR inline edit modal (fallback for narrow screens) */}
      {editingKr && !selectedOkr && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setEditingKr(null)}>
          <div style={{ background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 10, padding: 20, minWidth: 280 }} onClick={(e) => e.stopPropagation()}>
            <div style={{ fontWeight: 600, marginBottom: 12 }}>Update: {editingKr.metric}</div>
            <input type="number" value={editValue} onChange={(e) => setEditValue(e.target.value)} autoFocus
              style={{ width: "100%", padding: "8px 10px", fontSize: 14, background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--fg)", boxSizing: "border-box" }}
              onKeyDown={(e) => { if (e.key === "Enter") handleKrSave(); if (e.key === "Escape") setEditingKr(null); }}
            />
            <div style={{ marginTop: 10, display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setEditingKr(null)}>Cancel</button>
              <button className="primary" disabled={saving} onClick={handleKrSave}>{saving ? "Saving…" : "Save"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

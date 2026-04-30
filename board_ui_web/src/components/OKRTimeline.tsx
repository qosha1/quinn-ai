"use client";
import { useMemo, useRef, useEffect } from "react";
import type { OKRInfo, KeyResult } from "@/lib/types";

interface Props {
  okrs: OKRInfo[];
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

export function OKRTimeline({ okrs }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const now = useMemo(() => new Date(), []);

  const rows = useMemo(() => buildRows(okrs, now), [okrs, now]);

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
                  style={{ top: i * ROW_H + BAR_Y_OFFSET, height: BAR_H, left: `${x}%`, width: `${w}%` }}
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
    </div>
  );
}

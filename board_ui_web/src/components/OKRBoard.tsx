"use client";
import type { OKRInfo, KeyResult } from "@/lib/types";

interface Props {
  okrs: OKRInfo[];
}

const COLUMNS: Array<{ id: OKRInfo["status"]; label: string; icon: string; accent: string }> = [
  { id: "active",    label: "Active",    icon: "↻", accent: "#3fb950" },
  { id: "draft",     label: "Draft",     icon: "○", accent: "#58a6ff" },
  { id: "completed", label: "Completed", icon: "✓", accent: "#8b949e" },
  { id: "cancelled", label: "Cancelled", icon: "✕", accent: "#f85149" },
];

function krProgress(kr: KeyResult): number {
  if (kr.unit === "bool") return kr.current >= 1 ? 100 : 0;
  if (kr.target <= 0) return 0;
  return Math.min(100, Math.round((kr.current / kr.target) * 100));
}

function krLabel(kr: KeyResult): string {
  if (kr.unit === "bool") return kr.current >= 1 ? "✓ done" : "not yet";
  if (kr.unit === "%") return `${kr.current}% / ${kr.target}%`;
  return `${kr.current} / ${kr.target}${kr.unit ? ` ${kr.unit}` : ""}`;
}

function overallProgress(krs: KeyResult[]): number {
  if (krs.length === 0) return 0;
  return Math.round(krs.reduce((sum, kr) => sum + krProgress(kr), 0) / krs.length);
}

function OKRCard({ okr, childOKRs }: { okr: OKRInfo; childOKRs: OKRInfo[] }) {
  const pct = overallProgress(okr.key_results);
  const progressColor = pct >= 70 ? "#3fb950" : pct >= 40 ? "#d29922" : "#58a6ff";

  return (
    <div className="okr-card">
      <div className="okr-card__header">
        <span className="okr-card__owner">{okr.owner_name}</span>
        {okr.due_date && (
          <span className="okr-card__due">
            {new Date(okr.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
          </span>
        )}
      </div>

      <div className="okr-card__title">{okr.title}</div>

      {okr.key_results.length > 0 && (
        <div className="okr-card__krs">
          {okr.key_results.map((kr, i) => (
            <div key={i} className="okr-kr">
              <div className="okr-kr__row">
                <span className="okr-kr__metric">{kr.metric}</span>
                <span className="okr-kr__value">{krLabel(kr)}</span>
              </div>
              {kr.unit !== "bool" && (
                <div className="okr-kr__bar">
                  <div
                    className="okr-kr__bar-fill"
                    style={{ width: `${krProgress(kr)}%`, background: progressColor }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="okr-card__footer">
        {pct > 0 && (
          <div className="okr-card__overall">
            <div className="okr-card__overall-bar">
              <div style={{ width: `${pct}%`, background: progressColor, height: "100%", borderRadius: 2 }} />
            </div>
            <span style={{ color: progressColor, fontSize: 11, fontWeight: 600 }}>{pct}%</span>
          </div>
        )}
        {childOKRs.length > 0 && (
          <span className="okr-card__children">↳ {childOKRs.length} sub-OKR{childOKRs.length > 1 ? "s" : ""}</span>
        )}
      </div>
    </div>
  );
}

export function OKRBoard({ okrs }: Props) {
  const childMap = new Map<string, OKRInfo[]>();
  for (const okr of okrs) {
    if (okr.parent_id) {
      if (!childMap.has(okr.parent_id)) childMap.set(okr.parent_id, []);
      childMap.get(okr.parent_id)!.push(okr);
    }
  }

  // Show root OKRs per column, then sub-OKRs indented below
  const columns = COLUMNS.map((col) => ({
    ...col,
    roots: okrs.filter((o) => o.status === col.id && !o.parent_id),
    children: okrs.filter((o) => o.status === col.id && !!o.parent_id),
  }));

  const totalActive = okrs.filter((o) => o.status === "active").length;

  if (okrs.length === 0) {
    return <div className="empty-state" style={{ paddingTop: 60 }}>No OKRs yet</div>;
  }

  return (
    <div>
      <div className="section-title" style={{ marginBottom: 16 }}>
        {okrs.length} OKRs · {totalActive} active
      </div>
      <div className="work-board">
        {columns.map((col) => {
          const all = [...col.roots, ...col.children];
          return (
            <div key={col.id} className="work-column">
              <div className="work-column__header" style={{ borderTopColor: col.accent }}>
                <span style={{ color: col.accent }}>{col.icon}</span>
                <span className="work-column__label">{col.label}</span>
                <span className="work-column__count">{all.length}</span>
              </div>
              <div className="work-column__body">
                {all.length === 0 && <div className="work-column__empty">—</div>}
                {col.roots.map((okr) => (
                  <div key={okr.id}>
                    <OKRCard okr={okr} childOKRs={childMap.get(okr.id) ?? []} />
                    {(childMap.get(okr.id) ?? []).map((child) => (
                      <div key={child.id} style={{ paddingLeft: 12, borderLeft: `2px solid var(--border)`, marginLeft: 8 }}>
                        <OKRCard okr={child} childOKRs={[]} />
                      </div>
                    ))}
                  </div>
                ))}
                {col.children.filter((c) => !col.roots.find((r) => (childMap.get(r.id) ?? []).includes(c))).map((okr) => (
                  <OKRCard key={okr.id} okr={okr} childOKRs={[]} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

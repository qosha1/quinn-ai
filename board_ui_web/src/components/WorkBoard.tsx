"use client";
import type { Bead, Dependency } from "@/lib/beads-db";

interface Props {
  beads: Bead[];
  dependencies: Dependency[];
}

const COLUMNS: Array<{ id: Bead["status"] | "review"; label: string; icon: string; accent: string }> = [
  { id: "open",        label: "Open",        icon: "○",  accent: "#58a6ff" },
  { id: "in_progress", label: "In Progress", icon: "↻",  accent: "#d29922" },
  { id: "review",      label: "Review",      icon: "◑",  accent: "#a371f7" },
  { id: "blocked",     label: "Blocked",     icon: "✕",  accent: "#f85149" },
  { id: "closed",      label: "Closed",      icon: "✓",  accent: "#3fb950" },
];

const PRIORITY_LABELS: Record<number, string> = { 0: "P0", 1: "P1", 2: "P2", 3: "P3", 4: "P4" };
const PRIORITY_COLORS: Record<number, string> = {
  0: "#f85149", 1: "#db6d28", 2: "#d29922", 3: "#58a6ff", 4: "#8b949e",
};

function formatDue(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const diffDays = Math.floor((d.getTime() - today.getTime()) / 86400000);
  if (diffDays < 0) return `${Math.abs(diffDays)}d overdue`;
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function typeIcon(type: string): string {
  if (type === "bug") return "🐛";
  if (type === "feature") return "✦";
  if (type === "epic") return "⚡";
  if (type === "ask") return "?";
  return "·";
}

function BeadCard({ bead }: { bead: Bead }) {
  const isOverdue = bead.due_at && new Date(bead.due_at) < new Date() && bead.status !== "closed";
  const isOKR = bead.issue_type === "epic" || bead.labels.includes("okr");

  return (
    <div className="bead-card" style={{ borderColor: isOKR ? "#a371f7" : undefined }}>
      <div className="bead-card__header">
        <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
          <span className="bead-card__priority" style={{ background: PRIORITY_COLORS[bead.priority] }}>
            {PRIORITY_LABELS[bead.priority] ?? "P?"}
          </span>
          {isOKR && <span className="bead-card__label-badge">OKR</span>}
        </div>
        <span className="bead-card__type-icon" title={bead.issue_type}>{typeIcon(bead.issue_type)}</span>
      </div>

      <div className="bead-card__title">{bead.title}</div>

      <div className="bead-card__footer">
        {bead.due_at && (
          <span className="bead-card__due" style={{ color: isOverdue ? "var(--red)" : "var(--fg-muted)" }}>
            {formatDue(bead.due_at)}
          </span>
        )}
        {bead.assignee && (
          <span className="bead-card__assignee">@{bead.assignee}</span>
        )}
        <span className="bead-card__id">{bead.id.replace(/^[a-z]+-/, "")}</span>
      </div>
    </div>
  );
}

export function WorkBoard({ beads, dependencies }: Props) {
  const blockedIds = new Set(dependencies.filter((d) => d.type === "blocks").map((d) => d.issue_id));

  const columns = COLUMNS.map((col) => ({
    ...col,
    beads: beads.filter((b) => b.status === col.id),
  }));

  const totalOpen = beads.filter((b) => b.status !== "closed").length;

  if (beads.length === 0) {
    return (
      <div className="empty-state" style={{ paddingTop: 60 }}>
        No work items yet — workers will file issues here as they start tasks
      </div>
    );
  }

  return (
    <div>
      <div className="section-title" style={{ marginBottom: 16 }}>
        {beads.length} items · {totalOpen} open
      </div>
      <div className="work-board">
        {columns.map((col) => (
          <div key={col.id} className="work-column">
            <div className="work-column__header" style={{ borderTopColor: col.accent }}>
              <span style={{ color: col.accent }}>{col.icon}</span>
              <span className="work-column__label">{col.label}</span>
              <span className="work-column__count">{col.beads.length}</span>
            </div>
            <div className="work-column__body">
              {col.beads.length === 0 && (
                <div className="work-column__empty">—</div>
              )}
              {col.beads.map((b) => <BeadCard key={b.id} bead={b} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

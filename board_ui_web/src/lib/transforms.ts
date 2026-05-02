import type { OKRInfo, WorkerStatus, SessionState } from "./types";

export interface OKRNode extends OKRInfo {
  children: OKRNode[];
}

export function workerStatusLabel(status: WorkerStatus, sessionState: SessionState | null): string {
  if (status === "onboarding") return "Onboarding";
  if (status === "offboarding") return "Offboarding";
  if (status === "terminated") return "Terminated";
  if (status === "pending") return "Pending";
  // active
  if (sessionState === "running") return "Working";
  if (sessionState === "idle") return "Idle";
  if (sessionState === "starting") return "Starting";
  if (sessionState === "crashed") return "Crashed";
  return "Stopped";
}

export function sessionStateColor(state: SessionState | null): "green" | "yellow" | "red" | "gray" {
  if (state === "running") return "green";
  if (state === "idle") return "yellow";
  if (state === "starting") return "yellow";
  if (state === "crashed") return "red";
  return "gray";
}

export function buildOKRTree(flat: OKRInfo[]): OKRNode[] {
  const nodeMap = new Map<string, OKRNode>();
  for (const okr of flat) {
    nodeMap.set(okr.id, { ...okr, children: [] });
  }

  const roots: OKRNode[] = [];
  for (const node of nodeMap.values()) {
    if (node.parent_id && nodeMap.has(node.parent_id)) {
      nodeMap.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(amount);
}

export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  if (diffSecs < 60) return "just now";
  const diffMins = Math.floor(diffSecs / 60);
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays}d ago`;
}

export function formatAbsoluteTimestamp(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const timeStr = date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });

  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 86400000);
  const dateStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());

  if (dateStart.getTime() === todayStart.getTime()) return `Today ${timeStr}`;
  if (dateStart.getTime() === yesterdayStart.getTime()) return `Yesterday ${timeStr}`;
  return `${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}, ${timeStr}`;
}

export function priorityLabel(priority: number): string {
  return ["P0 Critical", "P1 High", "P2 Medium", "P3 Low", "P4 Backlog"][priority] ?? "Unknown";
}

export function formatElapsed(isoString: string | null): string {
  if (!isoString) return "";
  const ms = Date.now() - new Date(isoString).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return "<1m";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`;
}

export function formatCurrencyShort(n: number): string {
  if (n === 0) return "$0";
  if (n < 0.01) return `<$0.01`;
  if (n < 1) return `$${n.toFixed(2)}`;
  if (n < 1000) return `$${Math.round(n)}`;
  return `$${(n / 1000).toFixed(1)}k`;
}

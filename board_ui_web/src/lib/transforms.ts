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
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays}d ago`;
}

export function priorityLabel(priority: number): string {
  return ["P0 Critical", "P1 High", "P2 Medium", "P3 Low", "P4 Backlog"][priority] ?? "Unknown";
}

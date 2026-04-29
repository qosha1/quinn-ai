export type OrgStatus = "uninitialized" | "initialized" | "running" | "stopped";
export type WorkerStatus = "pending" | "onboarding" | "active" | "offboarding" | "terminated";
export type SessionState = "starting" | "idle" | "running" | "stopped" | "crashed";
export type WorkerRole = "ceo" | "director" | "manager" | "senior" | "worker";
export type OKRStatus = "draft" | "active" | "completed" | "cancelled";
export type MessagePriority = 0 | 1 | 2 | 3 | 4;
export type HealthScore = "healthy" | "warning" | "critical";

export interface WorkerInfo {
  id: string;
  name: string;
  role: WorkerRole;
  team_name: string;
  status: WorkerStatus;
  session_state: SessionState | null;
  manager_id: string | null;
  current_task: string | null;
  is_ceo: boolean;
}

export interface OrgInfo {
  name: string;
  status: OrgStatus;
  ceo_worker_id: string | null;
  worker_count: number;
  active_session_count: number;
  started_at: string | null;
  stopped_at: string | null;
}

export interface BudgetSummary {
  total_allocated: number;
  total_spent: number;
  total_available: number;
  spend_today: number;
  spend_this_week: number;
}

export interface HealthIssue {
  worker_id: string;
  worker_name: string;
  issue_type: string;
  severity: "info" | "warning" | "error";
  message: string;
}

export interface HealthStatus {
  overall_score: HealthScore;
  issues: HealthIssue[];
  workers_with_issues: number;
  total_workers: number;
}

export interface Message {
  id: string;
  from_worker_id: string;
  from_worker_name: string;
  channel_name: string;
  content: string;
  priority: MessagePriority;
  created_at: string;
  is_read: boolean;
}

export interface KeyResult {
  title: string;
  current: number;
  target: number;
  unit?: string;
}

export interface OKRInfo {
  id: string;
  title: string;
  description: string | null;
  owner_name: string;
  owner_id: string;
  status: OKRStatus;
  parent_id: string | null;
  key_results: KeyResult[];
  due_date: string | null;
  children_count: number;
}

export interface ActivityEntry {
  timestamp: string;
  worker_id: string;
  worker_name: string;
  event_type: string;
  summary: string;
}

export interface OrgDashboard {
  org: OrgInfo;
  budget: BudgetSummary;
  health: HealthStatus;
}

export interface Channel {
  id: string;
  name: string;
  channel_type: string;
  message_count: number;
  unread_count: number;
}

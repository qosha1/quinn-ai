"use client";
import type { WorkerInfo } from "@/lib/types";
import { workerStatusLabel, sessionStateColor } from "@/lib/transforms";

interface Props {
  worker: WorkerInfo;
  onAction: (workerId: string, action: "pause" | "resume" | "fire") => void;
  onClick?: () => void;
  focused?: boolean;
  sessionInfo?: string;
}

export function WorkerRow({ worker, onAction, onClick, focused, sessionInfo }: Props) {
  const color = sessionStateColor(worker.session_state);
  const label = workerStatusLabel(worker.status, worker.session_state);
  const roleDisplay = worker.is_ceo ? `★ ${worker.role.toUpperCase()}` : worker.role.toUpperCase();

  const runtimeDot = worker.runtime_status === "running" ? "#3fb950"
    : worker.runtime_status === "idle" ? "#d29922"
    : "#6e7681";

  return (
    <tr
      className="worker-row"
      onClick={onClick}
      style={{
        cursor: onClick ? "pointer" : undefined,
        background: focused ? "rgba(88,166,255,0.08)" : undefined,
        outline: focused ? "1px solid rgba(88,166,255,0.3)" : undefined,
      }}
    >
      <td>
        <span
          className={`status-dot status-dot--${color}`}
          title={`${label} · runtime: ${worker.runtime_status ?? "unknown"}`}
        />
      </td>
      <td>
        <span
          style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: runtimeDot, verticalAlign: "middle" }}
          title={`Runtime: ${worker.runtime_status ?? "unknown"}`}
        />
      </td>
      <td className="worker-name">{worker.name}</td>
      <td className="worker-role">{roleDisplay}</td>
      <td className="worker-team">{worker.team_name}</td>
      <td className="worker-status">{label}</td>
      <td style={{ fontSize: 11, color: "var(--fg-muted)", whiteSpace: "nowrap" }}>{sessionInfo ?? ""}</td>
      <td>
        <details className="action-menu" onClick={(e) => e.stopPropagation()}>
          <summary role="button" aria-label="Actions">⋮</summary>
          <div className="action-menu__items">
            {worker.session_state !== "stopped" && worker.session_state !== "crashed" && (
              <button onClick={() => onAction(worker.id, "pause")}>Pause</button>
            )}
            {(worker.session_state === "stopped" || worker.session_state === "idle") && (
              <button onClick={() => onAction(worker.id, "resume")}>Resume</button>
            )}
            {!worker.is_ceo && (
              <button className="danger" onClick={() => onAction(worker.id, "fire")}>Fire</button>
            )}
          </div>
        </details>
      </td>
    </tr>
  );
}

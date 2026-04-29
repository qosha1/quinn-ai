"use client";
import type { WorkerInfo } from "@/lib/types";
import { workerStatusLabel, sessionStateColor } from "@/lib/transforms";

interface Props {
  worker: WorkerInfo;
  onAction: (workerId: string, action: "pause" | "resume" | "fire") => void;
}

export function WorkerRow({ worker, onAction }: Props) {
  const color = sessionStateColor(worker.session_state);
  const label = workerStatusLabel(worker.status, worker.session_state);
  const roleDisplay = worker.is_ceo ? `★ ${worker.role.toUpperCase()}` : worker.role.toUpperCase();

  return (
    <tr className="worker-row">
      <td>
        <span
          className={`status-dot status-dot--${color}`}
          title={`${label} (${worker.session_state ?? "no session"})`}
        />
      </td>
      <td className="worker-name">{worker.name}</td>
      <td className="worker-role">{roleDisplay}</td>
      <td className="worker-team">{worker.team_name}</td>
      <td className="worker-status">{label}</td>
      <td>
        <details className="action-menu">
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

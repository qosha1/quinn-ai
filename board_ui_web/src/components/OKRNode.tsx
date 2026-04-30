"use client";
import type { OKRNode as OKRNodeType } from "@/lib/transforms";

interface Props {
  node: OKRNodeType;
  depth?: number;
}

export function OKRNode({ node, depth = 0 }: Props) {
  const progress = node.key_results.length > 0
    ? Math.round(node.key_results.reduce((sum, kr) => sum + (kr.target > 0 ? kr.current / kr.target : 0), 0) / node.key_results.length * 100)
    : null;

  const statusColors: Record<string, string> = {
    active: "var(--green)",
    completed: "var(--fg-muted)",
    draft: "var(--yellow)",
    cancelled: "var(--red)",
  };

  return (
    <div className="okr-node" style={{ paddingLeft: `${depth * 20}px` }}>
      <div className="okr-node__header">
        <span className="okr-node__status-dot" style={{ background: statusColors[node.status] ?? "var(--fg-muted)" }} />
        <span className="okr-node__title">{node.title}</span>
        <span className="okr-node__owner">{node.owner_name}</span>
        {progress !== null && (
          <span className="okr-node__progress">{progress}%</span>
        )}
      </div>
      {node.key_results.length > 0 && (
        <ul className="okr-node__krs">
          {node.key_results.map((kr, i) => (
            <li key={i} className="kr-item">
              <span className="kr-item__title">{kr.metric}</span>
              <span className="kr-item__value">{kr.current} / {kr.target}{kr.unit ? ` ${kr.unit}` : ""}</span>
              <div className="kr-item__bar">
                <div
                  className="kr-item__bar-fill"
                  style={{ width: `${Math.min(100, kr.target > 0 ? (kr.current / kr.target) * 100 : 0)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
      {node.children.map((child) => (
        <OKRNode key={child.id} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

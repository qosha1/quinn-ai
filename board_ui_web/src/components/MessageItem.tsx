"use client";
import type { Message } from "@/lib/types";
import { formatRelativeTime, priorityLabel } from "@/lib/transforms";

interface Props {
  message: Message;
  onReply: (messageId: string) => void;
  onMarkRead: (messageId: string) => void;
  isSelected?: boolean;
  onClick?: () => void;
}

export function MessageItem({ message, onReply, onMarkRead, isSelected, onClick }: Props) {
  const priorityColors = ["var(--red)", "var(--orange)", "var(--fg)", "var(--fg-muted)", "var(--fg-muted)"];

  return (
    <div
      className={`message-item ${isSelected ? "message-item--selected" : ""} ${!message.is_read ? "message-item--unread" : ""}`}
      onClick={onClick}
    >
      <div className="message-item__header">
        <span className="message-item__sender">{message.from_worker_name}</span>
        <span className="message-item__time">{formatRelativeTime(message.created_at)}</span>
        {!message.is_read && (
          <span className="unread-badge" title="unread">●</span>
        )}
        <span
          className="priority-badge"
          title={priorityLabel(message.priority)}
          style={{ color: priorityColors[message.priority] ?? "inherit" }}
        >
          {message.priority === 0 && <span>🔴</span>}
          {message.priority === 1 && <span>🟠</span>}
          {message.priority >= 2 && <span>⚪</span>}
        </span>
      </div>
      <div className="message-item__preview">{message.content.slice(0, 120)}{message.content.length > 120 ? "…" : ""}</div>
      <div className="message-item__actions">
        <button
          className="btn-sm"
          aria-label="Reply"
          onClick={(e) => { e.stopPropagation(); onReply(message.id); }}
        >
          Reply
        </button>
        {!message.is_read && (
          <button
            className="btn-sm btn-sm--ghost"
            onClick={(e) => { e.stopPropagation(); onMarkRead(message.id); }}
          >
            Mark read
          </button>
        )}
      </div>
    </div>
  );
}

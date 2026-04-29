import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MessageItem } from "@/components/MessageItem";
import type { Message } from "@/lib/types";

const mockMessage: Message = {
  id: "msg-1",
  from_worker_id: "w-1",
  from_worker_name: "Alice",
  channel_name: "board-channel",
  content: "Blocked on API credentials, need your help",
  priority: 0,
  created_at: new Date().toISOString(),
  is_read: false,
};

describe("MessageItem", () => {
  it("renders sender name", () => {
    render(<MessageItem message={mockMessage} onReply={() => {}} onMarkRead={() => {}} />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("renders message content preview", () => {
    render(<MessageItem message={mockMessage} onReply={() => {}} onMarkRead={() => {}} />);
    expect(screen.getByText(/Blocked on API credentials/i)).toBeInTheDocument();
  });

  it("shows unread badge when is_read=false", () => {
    render(<MessageItem message={mockMessage} onReply={() => {}} onMarkRead={() => {}} />);
    expect(screen.getByTitle(/unread/i)).toBeInTheDocument();
  });

  it("shows priority indicator for P0", () => {
    render(<MessageItem message={mockMessage} onReply={() => {}} onMarkRead={() => {}} />);
    expect(screen.getByTitle(/critical/i)).toBeInTheDocument();
  });

  it("calls onReply when reply button clicked", () => {
    const onReply = vi.fn();
    render(<MessageItem message={mockMessage} onReply={onReply} onMarkRead={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /reply/i }));
    expect(onReply).toHaveBeenCalledWith("msg-1");
  });
});

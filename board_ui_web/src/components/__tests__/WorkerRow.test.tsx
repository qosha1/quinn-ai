import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WorkerRow } from "@/components/WorkerRow";
import type { WorkerInfo } from "@/lib/types";

const mockWorker: WorkerInfo = {
  id: "w-1",
  name: "Alice",
  role: "ceo",
  team_name: "Engineering",
  status: "active",
  session_state: "running",
  runtime_status: "running",
  manager_id: null,
  current_task: "Reviewing proposals",
  is_ceo: true,
};

describe("WorkerRow", () => {
  it("renders worker name", () => {
    render(<WorkerRow worker={mockWorker} onAction={() => {}} />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("renders CEO role with star marker", () => {
    render(<WorkerRow worker={mockWorker} onAction={() => {}} />);
    expect(screen.getByText(/CEO/i)).toBeInTheDocument();
  });

  it("renders team name", () => {
    render(<WorkerRow worker={mockWorker} onAction={() => {}} />);
    expect(screen.getByText("Engineering")).toBeInTheDocument();
  });

  it("shows running status indicator", () => {
    render(<WorkerRow worker={mockWorker} onAction={() => {}} />);
    expect(screen.getAllByTitle(/running/i).length).toBeGreaterThan(0);
  });

  it("renders action menu button", () => {
    render(<WorkerRow worker={mockWorker} onAction={() => {}} />);
    expect(screen.getByRole("button", { name: /actions/i })).toBeInTheDocument();
  });
});

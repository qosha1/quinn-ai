import { describe, it, expect } from "vitest";
import { workerStatusLabel, sessionStateColor, buildOKRTree } from "@/lib/transforms";
import type { OKRInfo } from "@/lib/types";

describe("workerStatusLabel", () => {
  it("labels active running worker as Working", () => {
    expect(workerStatusLabel("active", "running")).toBe("Working");
  });

  it("labels active idle worker as Idle", () => {
    expect(workerStatusLabel("active", "idle")).toBe("Idle");
  });

  it("labels active stopped worker as Stopped", () => {
    expect(workerStatusLabel("active", "stopped")).toBe("Stopped");
  });

  it("labels active crashed worker as Crashed", () => {
    expect(workerStatusLabel("active", "crashed")).toBe("Crashed");
  });

  it("labels onboarding worker as Onboarding", () => {
    expect(workerStatusLabel("onboarding", null)).toBe("Onboarding");
  });

  it("labels terminated worker as Terminated", () => {
    expect(workerStatusLabel("terminated", null)).toBe("Terminated");
  });
});

describe("sessionStateColor", () => {
  it("returns green for running", () => {
    expect(sessionStateColor("running")).toBe("green");
  });

  it("returns yellow for idle", () => {
    expect(sessionStateColor("idle")).toBe("yellow");
  });

  it("returns red for crashed", () => {
    expect(sessionStateColor("crashed")).toBe("red");
  });

  it("returns gray for null/stopped", () => {
    expect(sessionStateColor(null)).toBe("gray");
    expect(sessionStateColor("stopped")).toBe("gray");
  });
});

describe("buildOKRTree", () => {
  const flat: OKRInfo[] = [
    {
      id: "okr-1",
      title: "Root OKR",
      description: null,
      owner_name: "Alice",
      owner_id: "w-1",
      status: "active",
      parent_id: null,
      key_results: [],
      due_date: null,
      children_count: 2,
    },
    {
      id: "okr-2",
      title: "Child OKR A",
      description: null,
      owner_name: "Bob",
      owner_id: "w-2",
      status: "active",
      parent_id: "okr-1",
      key_results: [],
      due_date: null,
      children_count: 0,
    },
    {
      id: "okr-3",
      title: "Child OKR B",
      description: null,
      owner_name: "Carol",
      owner_id: "w-3",
      status: "active",
      parent_id: "okr-1",
      key_results: [],
      due_date: null,
      children_count: 0,
    },
  ];

  it("returns only root nodes at top level", () => {
    const tree = buildOKRTree(flat);
    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("okr-1");
  });

  it("nests children under parent", () => {
    const tree = buildOKRTree(flat);
    expect(tree[0].children).toHaveLength(2);
  });

  it("handles empty input", () => {
    expect(buildOKRTree([])).toEqual([]);
  });
});

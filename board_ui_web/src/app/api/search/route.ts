import { NextResponse } from "next/server";
import { resolveDbPath, searchMessages, getWorkers, getOKRs } from "@/lib/db";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q")?.trim() ?? "";
  if (!q || q.length < 2) {
    return NextResponse.json({ results: [] });
  }
  const dbPath = resolveDbPath();
  const lq = q.toLowerCase();

  const results: Array<{
    type: "message" | "worker" | "okr";
    id: string;
    title: string;
    subtitle: string;
    tab: string;
  }> = [];

  // Messages
  try {
    const msgs = searchMessages(dbPath, q, undefined);
    for (const m of msgs) {
      results.push({
        type: "message",
        id: m.id,
        title: m.content.slice(0, 80),
        subtitle: `${m.from_worker_name} → #${m.channel_name}`,
        tab: "messages",
      });
    }
  } catch { /* ignore */ }

  // Workers
  try {
    const workers = getWorkers(dbPath);
    for (const w of workers) {
      if (w.name.toLowerCase().includes(lq) || w.role.toLowerCase().includes(lq)) {
        results.push({
          type: "worker",
          id: w.id,
          title: w.name,
          subtitle: w.role,
          tab: "team",
        });
      }
    }
  } catch { /* ignore */ }

  // OKRs
  try {
    const okrs = getOKRs(dbPath);
    for (const o of okrs) {
      if (o.title.toLowerCase().includes(lq) || (o.description ?? "").toLowerCase().includes(lq)) {
        results.push({
          type: "okr",
          id: o.id,
          title: o.title,
          subtitle: `OKR · ${o.owner_name}`,
          tab: "okrs",
        });
      }
    }
  } catch { /* ignore */ }

  return NextResponse.json({ results: results.slice(0, 12) }, {
    headers: { "Cache-Control": "no-store" },
  });
}

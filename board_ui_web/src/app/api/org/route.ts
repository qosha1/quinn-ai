import { NextResponse } from "next/server";
import { resolveDbPath, getOrgInfo, getBudgetSummary, getHealthStatus } from "@/lib/db";

export async function GET() {
  try {
    const dbPath = resolveDbPath();
    const [org, budget, health] = [getOrgInfo(dbPath), getBudgetSummary(dbPath), getHealthStatus(dbPath)];
    return NextResponse.json({ org, budget, health }, {
      headers: { "Cache-Control": "private, max-age=10, stale-while-revalidate=5" },
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

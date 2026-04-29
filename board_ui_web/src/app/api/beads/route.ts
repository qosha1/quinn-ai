import { NextResponse } from "next/server";
import { resolveBeadsDbPath, getBeads } from "@/lib/beads-db";

export async function GET() {
  try {
    const dbPath = resolveBeadsDbPath();
    if (!dbPath) {
      return NextResponse.json({ beads: [], dependencies: [], empty: true });
    }
    const data = getBeads(dbPath);
    return NextResponse.json(data, {
      headers: { "Cache-Control": "private, max-age=10, stale-while-revalidate=5" },
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

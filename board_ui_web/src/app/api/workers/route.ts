import { NextResponse } from "next/server";
import { resolveDbPath, getWorkers } from "@/lib/db";

export async function GET() {
  try {
    const workers = getWorkers(resolveDbPath());
    return NextResponse.json({ workers }, {
      headers: { "Cache-Control": "private, max-age=5, stale-while-revalidate=2" },
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

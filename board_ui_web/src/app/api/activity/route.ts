import { NextResponse } from "next/server";
import { resolveDbPath, getRecentActivity } from "@/lib/db";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const minutes = parseInt(searchParams.get("minutes") ?? "60", 10);
    const activity = getRecentActivity(resolveDbPath(), minutes);
    return NextResponse.json({ activity }, {
      headers: { "Cache-Control": "private, max-age=10, stale-while-revalidate=5" },
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

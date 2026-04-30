import { NextResponse } from "next/server";
import { resolveDbPath, searchMessages } from "@/lib/db";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const q = searchParams.get("q");
    if (!q?.trim()) return NextResponse.json({ results: [] });
    const channel = searchParams.get("channel") ?? undefined;
    const results = searchMessages(resolveDbPath(), q.trim(), channel);
    return NextResponse.json({ results });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

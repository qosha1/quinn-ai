import { NextResponse } from "next/server";
import { resolveDbPath, markChannelRead } from "@/lib/db";

export async function POST(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const channel = searchParams.get("channel");
    if (!channel) return NextResponse.json({ error: "channel required" }, { status: 400 });
    markChannelRead(resolveDbPath(), channel);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

import { NextResponse } from "next/server";
import { resolveDbPath, getMessages, getAllChannels } from "@/lib/db";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const channel = searchParams.get("channel") ?? "board-channel";
    const dbPath = resolveDbPath();

    if (channel === "_channels") {
      return NextResponse.json({ channels: getAllChannels(dbPath) });
    }

    const messages = getMessages(dbPath, channel);
    return NextResponse.json({ messages }, {
      headers: { "Cache-Control": "private, max-age=5, stale-while-revalidate=2" },
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

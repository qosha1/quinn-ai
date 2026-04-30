import { NextResponse } from "next/server";
import { resolveDbPath, getChannelsWithSubscription, getAllChannels } from "@/lib/db";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const workerId = searchParams.get("worker_id");
    const dbPath = resolveDbPath();
    if (workerId) {
      return NextResponse.json({ channels: getChannelsWithSubscription(dbPath, workerId) });
    }
    return NextResponse.json({ channels: getAllChannels(dbPath) });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

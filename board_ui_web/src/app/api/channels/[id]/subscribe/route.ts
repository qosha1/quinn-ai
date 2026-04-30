import { NextResponse } from "next/server";
import { resolveDbPath, subscribeToChannel, unsubscribeFromChannel } from "@/lib/db";

const BOARD_WORKER = "board-operator";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: channelId } = await params;
    subscribeToChannel(resolveDbPath(), channelId, BOARD_WORKER);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: channelId } = await params;
    unsubscribeFromChannel(resolveDbPath(), channelId, BOARD_WORKER);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

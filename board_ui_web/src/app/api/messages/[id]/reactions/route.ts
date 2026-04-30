import { NextResponse } from "next/server";
import { z } from "zod";
import { resolveDbPath, addReaction, removeReaction, getReactionCounts, getWorkers } from "@/lib/db";

const Schema = z.object({ emoji: z.string().min(1).max(10) });

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: messageId } = await params;
    const body = await request.json();
    const parsed = Schema.safeParse(body);
    if (!parsed.success) return NextResponse.json({ error: parsed.error.message }, { status: 400 });

    const dbPath = resolveDbPath();
    const ceo = getWorkers(dbPath).find((w) => w.is_ceo);
    const workerId = ceo?.id ?? "board-operator";
    addReaction(dbPath, messageId, workerId, parsed.data.emoji);
    return NextResponse.json({ counts: getReactionCounts(dbPath, messageId) });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: messageId } = await params;
    const body = await request.json();
    const parsed = Schema.safeParse(body);
    if (!parsed.success) return NextResponse.json({ error: parsed.error.message }, { status: 400 });

    const dbPath = resolveDbPath();
    const ceo = getWorkers(dbPath).find((w) => w.is_ceo);
    const workerId = ceo?.id ?? "board-operator";
    removeReaction(dbPath, messageId, workerId, parsed.data.emoji);
    return NextResponse.json({ counts: getReactionCounts(dbPath, messageId) });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

import { NextResponse } from "next/server";
import { z } from "zod";
import { resolveDbPath, markMessageRead, sendReply } from "@/lib/db";

const ReplySchema = z.object({
  content: z.string().min(1).max(10000),
});

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const parsed = ReplySchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json({ error: parsed.error.message }, { status: 400 });
    }

    const dbPath = resolveDbPath();
    const newId = sendReply(dbPath, id, parsed.data.content);
    markMessageRead(dbPath, id);
    return NextResponse.json({ ok: true, id: newId });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    markMessageRead(resolveDbPath(), id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

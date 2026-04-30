import { NextResponse } from "next/server";
import { z } from "zod";
import { resolveDbPath, createDirectChannel } from "@/lib/db";

const Schema = z.object({ worker_id: z.string().min(1) });

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const parsed = Schema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json({ error: parsed.error.message }, { status: 400 });
    }
    const dbPath = resolveDbPath();
    // Board operator DMs as CEO
    const { worker_id } = parsed.data;
    const channel = createDirectChannel(dbPath, "board-operator", worker_id);
    return NextResponse.json({ channel });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

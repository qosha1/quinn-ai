import { NextResponse } from "next/server";
import { z } from "zod";
import { resolveDbPath, postMessageToChannel, getWorkers } from "@/lib/db";

const PostSchema = z.object({
  content: z.string().min(1).max(10000),
  priority: z.number().int().min(0).max(4).optional(),
});

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: channelId } = await params;
    const body = await request.json();
    const parsed = PostSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json({ error: parsed.error.message }, { status: 400 });
    }

    const dbPath = resolveDbPath();
    // Board operator sends as CEO
    const workers = getWorkers(dbPath);
    const ceo = workers.find((w) => w.is_ceo);
    if (!ceo) return NextResponse.json({ error: "No CEO found" }, { status: 500 });

    const msg = postMessageToChannel(dbPath, channelId, ceo.id, parsed.data.content, parsed.data.priority ?? 2);
    return NextResponse.json({ message: msg });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

import { resolveDbPath, getMessages } from "@/lib/db";

const POLL_MS = 2000;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const channel = searchParams.get("channel") ?? "general";

  const encoder = new TextEncoder();

  function encode(event: string, data: unknown): Uint8Array {
    return encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  }

  const stream = new ReadableStream({
    async start(controller) {
      // Emit connected immediately so tests can verify content-type + body
      controller.enqueue(encode("connected", { channel }));

      let lastCount = 0;
      let lastTs = "";

      // Seed initial state
      try {
        const dbPath = resolveDbPath();
        const msgs = getMessages(dbPath, channel);
        lastCount = msgs.length;
        lastTs = msgs.at(-1)?.created_at ?? "";
      } catch { /* DB not available in test env */ }

      // Poll for new messages — abort when client disconnects
      const signal = request.signal;
      while (!signal.aborted) {
        await new Promise((r) => setTimeout(r, POLL_MS));
        if (signal.aborted) break;
        try {
          const dbPath = resolveDbPath();
          const msgs = getMessages(dbPath, channel);
          const newMsgs = msgs.filter((m) => m.created_at > lastTs);
          if (newMsgs.length > 0) {
            controller.enqueue(encode("messages", { messages: newMsgs }));
            lastTs = msgs.at(-1)?.created_at ?? lastTs;
            lastCount = msgs.length;
          }
        } catch { /* ignore poll errors */ }
      }

      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

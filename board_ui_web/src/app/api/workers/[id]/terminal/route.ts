import { execSync } from "child_process";
import { resolveDbPath } from "@/lib/db";
import Database from "better-sqlite3";

function getTmuxSession(orgPath: string, workerId: string): string | null {
  const db = new Database(resolveDbPath(), { readonly: true });
  try {
    const row = db.prepare(
      `SELECT tmux_session_name FROM sessions
       WHERE worker_id = ? AND state IN ('running','starting','idle')
       ORDER BY created_at DESC LIMIT 1`
    ).get(workerId) as { tmux_session_name: string } | undefined;
    return row?.tmux_session_name ?? null;
  } finally {
    db.close();
  }
}

// eslint-disable-next-line no-control-regex
const ANSI_STRIP = /\x1b\[[0-9;]*[mGKJHFABCDhls]|\x1b\][^\x07]*\x07|\x1b[()][AB012]/g;

function capturePane(session: string, lines: number): string {
  try {
    const raw = execSync(
      `tmux capture-pane -t ${session} -p | tail -${lines}`,
      { timeout: 2000, stdio: ["ignore", "pipe", "pipe"] }
    ).toString();
    return raw.replace(ANSI_STRIP, "");
  } catch {
    return "";
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const orgPath = process.env.QUINN_ORG_PATH ?? process.cwd();
  const { searchParams } = new URL(request.url);
  const lines = Math.min(parseInt(searchParams.get("lines") ?? "40"), 100);

  const session = getTmuxSession(orgPath, id);
  if (!session) {
    return new Response(
      JSON.stringify({ error: "No active tmux session", content: "" }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  }

  const content = capturePane(session, lines);

  // SSE stream: emit one snapshot, then poll every 2s
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const emit = (data: string) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ session, content: data })}\n\n`));
      };

      emit(content);

      let alive = true;
      request.signal.addEventListener("abort", () => { alive = false; });

      while (alive) {
        await new Promise((r) => setTimeout(r, 2000));
        if (!alive) break;
        try {
          emit(capturePane(session, lines));
        } catch {
          break;
        }
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  });
}

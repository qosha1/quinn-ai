import { NextResponse } from "next/server";
import { z } from "zod";
import { execSync } from "child_process";
import path from "path";

const ActionSchema = z.object({
  action: z.enum(["pause", "resume", "fire"]),
  reason: z.string().optional(),
});

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const parsed = ActionSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json({ error: parsed.error.message }, { status: 400 });
    }

    const { action, reason } = parsed.data;
    const orgPath = process.env.QUINN_ORG_PATH ?? process.cwd();
    const qnBin = path.join(orgPath, "..", "..", "quinn-ai", ".venv", "bin", "qn");
    const reasonFlag = reason ? `--reason "${reason.replace(/"/g, '\\"')}"` : "";

    const cmd = action === "pause"
      ? `${qnBin} board intervene pause ${id} ${reasonFlag}`
      : action === "resume"
      ? `${qnBin} board intervene resume ${id}`
      : `${qnBin} board intervene fire ${id} ${reasonFlag}`;

    execSync(cmd, { cwd: orgPath, timeout: 10000 });
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

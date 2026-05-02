import { NextResponse } from "next/server";
import { execSync } from "child_process";
import path from "path";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const orgPath = process.env.QUINN_ORG_PATH ?? process.cwd();

  try {
    // Run bd list filtered by assignee — works with both sqlite and dolt backends
    const beadsDir = path.join(orgPath, ".beads");
    const out = execSync(
      `bd list --assignee=${id} --status=open,in_progress --json --limit=5`,
      {
        env: { ...process.env, BEADS_DIR: beadsDir },
        timeout: 5000,
        stdio: ["ignore", "pipe", "pipe"],
      }
    ).toString();
    const data = JSON.parse(out);
    const issues = Array.isArray(data) ? data : (data.issues ?? data.beads ?? []);
    const inProgress = issues.filter((i: { status: string }) => i.status === "in_progress");
    const open = issues.filter((i: { status: string }) => i.status !== "in_progress");
    return NextResponse.json({ in_progress: inProgress, open }, {
      headers: { "Cache-Control": "private, max-age=15" },
    });
  } catch {
    return NextResponse.json({ in_progress: [], open: [] });
  }
}

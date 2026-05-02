import { NextResponse } from "next/server";
import { z } from "zod";
import { resolveDbPath } from "@/lib/db";
import Database from "better-sqlite3";

const PatchSchema = z.object({
  metric: z.string().min(1),
  current: z.number(),
});

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const parsed = PatchSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json({ error: parsed.error.message }, { status: 400 });
    }
    const { metric, current } = parsed.data;
    const db = new Database(resolveDbPath(), { readonly: false });
    try {
      const result = db.prepare(
        `UPDATE okr_key_results SET current_value = ? WHERE okr_id = ? AND metric = ?`
      ).run(current, id, metric);
      if (result.changes === 0) {
        return NextResponse.json({ error: "OKR or metric not found" }, { status: 404 });
      }
      return NextResponse.json({ ok: true, okr_id: id, metric, current });
    } finally {
      db.close();
    }
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

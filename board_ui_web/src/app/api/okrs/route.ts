import { NextResponse } from "next/server";
import { resolveDbPath, getOKRs } from "@/lib/db";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const ownerId = searchParams.get("owner") ?? undefined;
    const okrs = getOKRs(resolveDbPath(), ownerId);
    return NextResponse.json({ okrs }, {
      headers: { "Cache-Control": "private, max-age=30, stale-while-revalidate=10" },
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

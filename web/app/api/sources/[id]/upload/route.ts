import { NextRequest } from "next/server";

import { apiRequest, proxyJSON } from "@/lib/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 3600;

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const contentType = request.headers.get("content-type");
  const init: RequestInit & { duplex: "half" } = {
    method: "POST",
    body: request.body,
    duplex: "half",
    headers: contentType ? { "Content-Type": contentType } : undefined,
  };
  return proxyJSON(await apiRequest(`/api/v1/sources/${encodeURIComponent(id)}/upload`, init));
}

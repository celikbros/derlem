import type { NextRequest } from "next/server";

import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const limit = request.nextUrl.searchParams.get("limit") ?? "100";
  return proxyJSON(
    await apiRequest(`/api/v1/similarity-calibrations/${encodeURIComponent(id)}/pairs?limit=${encodeURIComponent(limit)}`),
  );
}

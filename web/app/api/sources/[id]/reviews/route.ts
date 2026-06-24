import { NextRequest } from "next/server";

import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return proxyJSON(await apiRequest(`/api/v1/sources/${encodeURIComponent(id)}/reviews`));
}

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return proxyJSON(
    await apiRequest(`/api/v1/sources/${encodeURIComponent(id)}/reviews`, {
      method: "POST",
      body: await request.text(),
    }),
  );
}

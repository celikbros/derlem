import { NextRequest } from "next/server";

import { apiRequest, proxyJSON } from "@/lib/api";

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyJSON(
    await apiRequest(`/api/v1/users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: await request.text(),
    }),
  );
}

import { NextRequest } from "next/server";

import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.search;
  return proxyJSON(await apiRequest(`/api/v1/sources${query}`));
}

export async function POST(request: NextRequest) {
  return proxyJSON(
    await apiRequest("/api/v1/sources", {
      method: "POST",
      body: await request.text(),
    }),
  );
}

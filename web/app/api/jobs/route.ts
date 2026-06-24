import { NextRequest } from "next/server";

import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET(request: NextRequest) {
  return proxyJSON(await apiRequest(`/api/v1/jobs${request.nextUrl.search}`));
}

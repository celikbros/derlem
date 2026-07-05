import { NextRequest } from "next/server";

import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET() {
  return proxyJSON(await apiRequest("/api/v1/users"));
}

export async function POST(request: NextRequest) {
  return proxyJSON(
    await apiRequest("/api/v1/users", {
      method: "POST",
      body: await request.text(),
    }),
  );
}

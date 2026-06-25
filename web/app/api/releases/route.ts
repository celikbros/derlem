import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET() {
  return proxyJSON(await apiRequest("/api/v1/releases?limit=200"));
}

export async function POST(request: Request) {
  return proxyJSON(await apiRequest("/api/v1/releases", {
    method: "POST",
    body: await request.text(),
  }));
}

import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET() {
  return proxyJSON(await apiRequest("/api/v1/similarity-calibrations"));
}

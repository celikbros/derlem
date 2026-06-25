import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  return proxyJSON(await apiRequest(`/api/v1/releases/${encodeURIComponent(id)}`));
}

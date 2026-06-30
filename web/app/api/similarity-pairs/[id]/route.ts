import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET(_: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return proxyJSON(await apiRequest(`/api/v1/similarity-pairs/${encodeURIComponent(id)}`));
}

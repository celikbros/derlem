import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const url = new URL(request.url);
  const limit = url.searchParams.get("limit") ?? "200";
  return proxyJSON(
    await apiRequest(`/api/v1/sources/${encodeURIComponent(id)}/documents?limit=${encodeURIComponent(limit)}`),
  );
}

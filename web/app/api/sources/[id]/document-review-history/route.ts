import { apiRequest, proxyJSON } from "@/lib/api";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { id } = await context.params;
  return proxyJSON(
    await apiRequest(
      `/api/v1/sources/${encodeURIComponent(id)}/document-review-history`,
    ),
  );
}

import { apiRequest, proxyJSON } from "@/lib/api";

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  return proxyJSON(await apiRequest(
    `/api/v1/sources/${encodeURIComponent(id)}/documents/resample`,
    { method: "POST" },
  ));
}

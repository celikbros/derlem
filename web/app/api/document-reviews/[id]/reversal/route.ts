import { apiRequest, proxyJSON } from "@/lib/api";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  return proxyJSON(
    await apiRequest(`/api/v1/document-reviews/${encodeURIComponent(id)}/reversal`, {
      method: "POST",
      body: await request.text(),
    }),
  );
}

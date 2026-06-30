import { apiRequest, proxyJSON } from "@/lib/api";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return proxyJSON(
    await apiRequest(`/api/v1/similarity-pairs/${encodeURIComponent(id)}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
    }),
  );
}

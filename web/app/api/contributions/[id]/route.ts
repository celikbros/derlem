import { apiRequest, proxyJSON } from "@/lib/api";

export async function DELETE(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const response = await apiRequest(
    `/api/v1/contributions/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  if (response.status === 204) return new Response(null, { status: 204 });
  return proxyJSON(response);
}

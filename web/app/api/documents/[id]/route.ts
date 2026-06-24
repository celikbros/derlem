import { apiRequest, proxyJSON } from "@/lib/api";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  return proxyJSON(await apiRequest(`/api/v1/documents/${encodeURIComponent(id)}`));
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  return proxyJSON(
    await apiRequest(`/api/v1/documents/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: await request.text(),
    }),
  );
}

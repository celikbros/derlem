import { apiRequest, proxyJSON } from "@/lib/api";

export async function POST(
  _request: Request,
  context: { params: Promise<{ token: string }> },
) {
  const { token } = await context.params;
  return proxyJSON(await apiRequest(
    `/api/v1/document-review-claims/${encodeURIComponent(token)}/renew`,
    { method: "POST" },
  ));
}

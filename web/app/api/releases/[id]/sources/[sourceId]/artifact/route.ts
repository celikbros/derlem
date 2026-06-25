import { apiRequest } from "@/lib/api";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string; sourceId: string }> },
) {
  const { id, sourceId } = await context.params;
  const response = await apiRequest(
    `/api/v1/releases/${encodeURIComponent(id)}/sources/${encodeURIComponent(sourceId)}/artifact`,
  );
  const headers = new Headers();
  for (const name of ["content-type", "content-length", "content-disposition", "etag"]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(response.body, { status: response.status, headers });
}

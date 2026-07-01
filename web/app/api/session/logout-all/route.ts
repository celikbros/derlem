import { cookies } from "next/headers";

import { apiRequest, proxyJSON } from "@/lib/api";

export async function POST() {
  const response = await apiRequest("/api/v1/auth/logout-all", { method: "POST" });
  if (!response.ok && response.status !== 401) {
    return proxyJSON(response);
  }
  const cookieStore = await cookies();
  cookieStore.delete("derlem_token");
  return proxyJSON(response);
}

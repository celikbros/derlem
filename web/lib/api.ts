import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const API_URL = process.env.DERLEM_API_URL ?? "http://localhost:8080";

export async function apiRequest(path: string, init: RequestInit = {}) {
  const cookieStore = await cookies();
  const token = cookieStore.get("derlem_token")?.value;
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}
export async function proxyJSON(response: Response) {
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}

import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.DERLEM_API_URL ?? "http://127.0.0.1:18401";

export async function POST(request: NextRequest) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const realIP = request.headers.get("x-real-ip");
  if (realIP) headers.set("X-Real-IP", realIP);
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers,
    body: await request.text(),
    cache: "no-store",
  });
  const payload = await response.json();
  if (!response.ok) {
    const retryAfter = response.headers.get("Retry-After");
    return NextResponse.json(payload, {
      status: response.status,
      headers: retryAfter ? { "Retry-After": retryAfter } : undefined,
    });
  }

  const expiresAt = new Date(payload.expires_at);
  const cookieStore = await cookies();
  cookieStore.set("derlem_token", payload.access_token, {
    httpOnly: true,
    sameSite: "lax",
    // DERLEM_COOKIE_SECURE=false yalnız güvenilir ofis ağında düz HTTP ile
    // erişim içindir (docs/ofis_kurulumu.md); Secure çerez HTTPS dışına
    // yazılmadığından bu kaçış olmadan LAN girişleri sessizce düşer.
    // İnternete açık production'da asla kullanmayın.
    secure: process.env.DERLEM_COOKIE_SECURE === "false" ? false : process.env.NODE_ENV === "production",
    path: "/",
    expires: expiresAt,
  });
  return NextResponse.json({ user: payload.user, expires_at: payload.expires_at });
}

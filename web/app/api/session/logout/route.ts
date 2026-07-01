import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { apiRequest, proxyJSON } from "@/lib/api";

export async function POST() {
	const response = await apiRequest("/api/v1/auth/logout", { method: "POST" });
	if (!response.ok && response.status !== 401) {
		return proxyJSON(response);
	}
	const cookieStore = await cookies();
	cookieStore.delete("derlem_token");
	return NextResponse.json({ status: "ok" });
}

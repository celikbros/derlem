import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function POST() {
  const cookieStore = await cookies();
  cookieStore.delete("derlem_token");
  return NextResponse.json({ status: "ok" });
}

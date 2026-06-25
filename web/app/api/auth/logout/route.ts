import { NextResponse } from "next/server";

import { clearAuthCookies } from "@/lib/authCookies";

// 로그아웃 BFF — 세션 쿠키(dh_token·dh_uid·dh_name) 제거.
export async function POST() {
  return clearAuthCookies(NextResponse.json({ ok: true }));
}

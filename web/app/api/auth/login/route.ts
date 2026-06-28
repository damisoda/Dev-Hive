import { NextResponse } from "next/server";

import { setAuthCookies } from "@/lib/authCookies";

// 로그인 BFF — 백엔드 /auth/login(아이디·비번) 호출 후 JWT를 httpOnly 쿠키로 심는다.

const API = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  let res: Response;
  try {
    res = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "백엔드에 연결할 수 없습니다." }, { status: 502 });
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // 401 등은 "아이디 또는 비밀번호가 올바르지 않습니다"로 통일(존재 여부 비노출).
    return NextResponse.json(
      { error: "아이디 또는 비밀번호가 올바르지 않습니다." },
      { status: res.status }
    );
  }

  const d = data as { access_token: string; user_id: number; display_name: string };
  const r = NextResponse.json({ user_id: d.user_id, display_name: d.display_name });
  return setAuthCookies(r, d);
}

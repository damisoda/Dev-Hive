import { NextResponse } from "next/server";

import { setAuthCookies } from "@/lib/authCookies";

// 회원가입 BFF — 브라우저가 제출, 서버가 백엔드 /auth/signup 호출(CORS 회피) 후
// 발급된 JWT를 httpOnly 쿠키로 심는다. 토큰은 브라우저 JS에 노출되지 않는다.

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
    res = await fetch(`${API}/auth/signup`, {
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
    return NextResponse.json(
      { error: (data as { detail?: string }).detail ?? "가입에 실패했습니다." },
      { status: res.status }
    );
  }

  const d = data as { access_token: string; user_id: number; display_name: string };
  // 토큰은 쿠키로만, 응답 바디엔 비밀 미포함.
  const r = NextResponse.json({ user_id: d.user_id, display_name: d.display_name });
  return setAuthCookies(r, d);
}

import { NextResponse } from "next/server";
import { UID_COOKIE, NAME_COOKIE } from "@/lib/session";

// BFF — 브라우저는 이 Route Handler에 제출, 서버가 백엔드 /auth/profile 호출(CORS 회피) 후
// 결과 user_id를 httpOnly 쿠키로 심는다(토큰 아님, 단순 식별자).

const API = process.env.API_BASE_URL ?? "http://localhost:8000";
const MAX_AGE = 60 * 60 * 24 * 30; // 30일

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  let res: Response;
  try {
    res = await fetch(`${API}/auth/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "백엔드에 연결할 수 없습니다." }, { status: 502 });
  }

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    return NextResponse.json(
      { error: (detail as { detail?: string }).detail ?? "가입에 실패했습니다." },
      { status: res.status }
    );
  }

  const data = (await res.json()) as { user_id: number; display_name: string };
  const r = NextResponse.json(data);
  const opts = { httpOnly: true, sameSite: "lax" as const, path: "/", maxAge: MAX_AGE };
  r.cookies.set(UID_COOKIE, String(data.user_id), opts);
  r.cookies.set(NAME_COOKIE, data.display_name, opts);
  return r;
}

// 로그아웃 — 세션 쿠키 제거.
export async function DELETE() {
  const r = NextResponse.json({ ok: true });
  r.cookies.delete(UID_COOKIE);
  r.cookies.delete(NAME_COOKIE);
  return r;
}

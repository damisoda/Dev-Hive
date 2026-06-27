import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { NAME_COOKIE, TOKEN_COOKIE } from "@/lib/session";

const API = process.env.API_BASE_URL ?? "http://localhost:8000";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 14;

async function getToken(): Promise<string | null> {
  const c = await cookies();
  return c.get(TOKEN_COOKIE)?.value ?? null;
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function GET() {
  const token = await getToken();
  if (!token) {
    return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  }

  let res: Response;
  try {
    res = await fetch(`${API}/auth/me`, {
      headers: authHeaders(token),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "백엔드에 연결할 수 없습니다." }, { status: 502 });
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return NextResponse.json(
      { error: (data as { detail?: string }).detail ?? "프로필을 불러오지 못했습니다." },
      { status: res.status }
    );
  }
  return NextResponse.json(data);
}

export async function PATCH(req: Request) {
  const token = await getToken();
  if (!token) {
    return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  let res: Response;
  try {
    res = await fetch(`${API}/auth/me`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "백엔드에 연결할 수 없습니다." }, { status: 502 });
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return NextResponse.json(
      { error: (data as { detail?: string }).detail ?? "프로필 저장에 실패했습니다." },
      { status: res.status }
    );
  }

  const response = NextResponse.json(data);
  const displayName = (data as { display_name?: string }).display_name;
  if (displayName) {
    response.cookies.set(NAME_COOKIE, displayName, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: COOKIE_MAX_AGE,
      secure: process.env.NODE_ENV === "production",
    });
  }
  return response;
}

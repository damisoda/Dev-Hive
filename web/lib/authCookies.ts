import { NextResponse } from "next/server";

import { NAME_COOKIE, TOKEN_COOKIE, UID_COOKIE } from "./session";

// JWT 만료(백엔드 14일)와 정렬. dh_token=서명 자격증명, dh_uid/dh_name=표시용 보조.
const MAX_AGE = 60 * 60 * 24 * 14;

export function setAuthCookies(
  res: NextResponse,
  data: { access_token: string; user_id: number; display_name: string }
): NextResponse {
  const base = {
    httpOnly: true,
    sameSite: "lax" as const,
    path: "/",
    maxAge: MAX_AGE,
    secure: process.env.NODE_ENV === "production",
  };
  res.cookies.set(TOKEN_COOKIE, data.access_token, base);
  res.cookies.set(UID_COOKIE, String(data.user_id), base);
  res.cookies.set(NAME_COOKIE, data.display_name, base);
  return res;
}

export function clearAuthCookies(res: NextResponse): NextResponse {
  res.cookies.delete(TOKEN_COOKIE);
  res.cookies.delete(UID_COOKIE);
  res.cookies.delete(NAME_COOKIE);
  return res;
}

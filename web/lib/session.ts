import { cookies } from "next/headers";

// HIVE-100: 정식 인증. 회원가입/로그인 시 백엔드가 발급한 서명 JWT를 httpOnly 쿠키
// (dh_token)에 저장하고, 개인화 요청은 이 토큰을 Authorization: Bearer로 전달한다.
// dh_uid/dh_name은 UI 표시용 보조값(신뢰하지 않음 — 인증은 오직 dh_token 서명).

export const TOKEN_COOKIE = "dh_token";
export const UID_COOKIE = "dh_uid";
export const NAME_COOKIE = "dh_name";

export interface Session {
  userId: number;
  displayName: string | null;
  token: string;
}

export async function getSession(): Promise<Session | null> {
  const c = await cookies();
  const token = c.get(TOKEN_COOKIE)?.value;
  const uid = c.get(UID_COOKIE)?.value;
  // 인증 게이트 = 서명 토큰 존재. uid는 표시용 보조.
  if (!token || !uid || Number.isNaN(Number(uid))) return null;
  return { userId: Number(uid), displayName: c.get(NAME_COOKIE)?.value ?? null, token };
}

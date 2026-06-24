import { cookies } from "next/headers";

// 프로토타입 세션 — 정식 인증 없음. 회원가입(/auth/profile) 시 발급한 user_id를
// httpOnly 쿠키에 저장하고, 개인화 표면(커리큘럼/추천)이 이걸로 현재 유저를 식별한다.

export const UID_COOKIE = "dh_uid";
export const NAME_COOKIE = "dh_name";

export interface Session {
  userId: number;
  displayName: string | null;
}

export async function getSession(): Promise<Session | null> {
  const c = await cookies();
  const uid = c.get(UID_COOKIE)?.value;
  if (!uid || Number.isNaN(Number(uid))) return null;
  return { userId: Number(uid), displayName: c.get(NAME_COOKIE)?.value ?? null };
}

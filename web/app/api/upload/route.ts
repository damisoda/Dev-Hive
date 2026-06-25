import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { UID_COOKIE } from "@/lib/session";

// 글 올리기 BFF — dh_uid 쿠키로 user_id 주입해 백엔드 POST /content.
// 백엔드는 태깅·임베딩·Auto-HKG 편입까지 동기 처리(수십 초 가능) → 넉넉한 타임아웃.

const API = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const uid = (await cookies()).get(UID_COOKIE)?.value;
  if (!uid) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });

  const b = (await req.json().catch(() => null)) as
    | { title?: string; body?: string; url?: string }
    | null;
  if (!b?.title?.trim() || !b?.body?.trim()) {
    return NextResponse.json({ error: "제목과 본문을 입력하세요." }, { status: 400 });
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 120_000);
  try {
    const r = await fetch(`${API}/content`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-User-Id": uid },
      body: JSON.stringify({
        title: b.title.trim(),
        body: b.body.trim(),
        url: b.url?.trim() || null,
      }),
      cache: "no-store",
      signal: ctrl.signal,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { error: (data as { detail?: string }).detail ?? "업로드에 실패했어요." },
        { status: r.status }
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "업로드 처리가 지연되거나 실패했어요. 잠시 후 다시 시도하세요." },
      { status: 504 }
    );
  } finally {
    clearTimeout(timer);
  }
}

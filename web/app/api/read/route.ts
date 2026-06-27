import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { TOKEN_COOKIE } from "@/lib/session";

// '읽기' BFF — 재가공본(공개, 캐시 우선) 조회 + 로그인 시 읽음 처리(PATCH /progress).
// 재가공본 조회는 인증 불필요(표시 전용). 읽음은 dh_token(JWT)이 있을 때만.

const API = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as { content_id?: number } | null;
  if (!body?.content_id) {
    return NextResponse.json({ error: "content_id가 필요합니다." }, { status: 400 });
  }
  const cid = body.content_id;

  let synthesis: unknown = null;
  let content_type: string | null = null;
  let url: string | null = null;
  try {
    const r = await fetch(`${API}/content/${cid}/synthesis`, { cache: "no-store" });
    if (r.ok) {
      const d = (await r.json()) as {
        synthesis?: unknown;
        content_type?: string | null;
        url?: string | null;
      };
      synthesis = d.synthesis ?? null;
      content_type = d.content_type ?? null;
      url = d.url ?? null;
    }
  } catch {
    /* 재가공본 실패는 graceful — 아래 읽음은 계속 */
  }

  let leveled_up = false;
  let new_level: string | null = null;
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (token) {
    try {
      const r = await fetch(`${API}/progress`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content_id: cid }),
        cache: "no-store",
      });
      if (r.ok) {
        const d = (await r.json()) as { leveled_up?: boolean; new_level?: string | null };
        leveled_up = Boolean(d.leveled_up);
        new_level = d.new_level ?? null;
      }
    } catch {
      /* 읽음 실패해도 재가공본은 반환 */
    }
  }

  return NextResponse.json({ synthesis, content_type, url, leveled_up, new_level });
}

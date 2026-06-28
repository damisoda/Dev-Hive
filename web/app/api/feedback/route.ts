import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { TOKEN_COOKIE } from "@/lib/session";

// BFF — 브라우저가 이 라우트에 제출, 서버가 dh_token(JWT)을 Authorization: Bearer로 주입해
// 백엔드 /feedback 호출(CORS 회피 + 서명검증으로 본인 강제). HIVE-100 백엔드와 짝.

const API = process.env.API_BASE_URL ?? "http://localhost:8000";

async function currentToken(): Promise<string | null> {
  const c = await cookies();
  return c.get(TOKEN_COOKIE)?.value ?? null;
}

async function forward(method: "PUT" | "DELETE", body: Record<string, unknown>) {
  const token = await currentToken();
  if (!token) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  let res: Response;
  try {
    res = await fetch(`${API}/feedback`, {
      method,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "백엔드에 연결할 수 없습니다." }, { status: 502 });
  }
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    return NextResponse.json(
      { error: (d as { detail?: string }).detail ?? "피드백 처리에 실패했습니다." },
      { status: res.status }
    );
  }
  return NextResponse.json(await res.json().catch(() => ({ status: "ok" })));
}

export async function PUT(req: Request) {
  const b = (await req.json().catch(() => null)) as { content_id?: number; feedback?: string } | null;
  if (!b?.content_id || !b?.feedback) {
    return NextResponse.json({ error: "content_id·feedback이 필요합니다." }, { status: 400 });
  }
  return forward("PUT", { content_id: b.content_id, feedback: b.feedback });
}

export async function DELETE(req: Request) {
  const b = (await req.json().catch(() => null)) as { content_id?: number } | null;
  if (!b?.content_id) {
    return NextResponse.json({ error: "content_id가 필요합니다." }, { status: 400 });
  }
  return forward("DELETE", { content_id: b.content_id });
}

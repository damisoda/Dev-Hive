// 백엔드 API 순수 fetch 클라이언트 — frontend/lib/api.py 의 TS 이식(1:1 변환 목표).
// 서버 컴포넌트에서만 호출(서버→백엔드 직결이라 CORS 불필요). 실패는 ApiError(한국어)로 통일.

import type {
  ContentListResponse,
  RecommendResponse,
  GraphResponse,
  MasteryResponse,
  ReadHistoryResponse,
  Profile,
  Stats,
  UserStateResponse,
} from "./types";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  isConnection: boolean;
  statusCode?: number;
  constructor(message: string, opts: { isConnection?: boolean; statusCode?: number } = {}) {
    super(message);
    this.name = "ApiError";
    this.isConnection = opts.isConnection ?? false;
    this.statusCode = opts.statusCode;
  }
}

interface RequestOpts {
  params?: Record<string, string | number | undefined>;
  timeoutMs?: number;
  headers?: Record<string, string>; // 개인화 요청용 Authorization 등
}

// HIVE-100: 서명 JWT를 Bearer로 전달. 백엔드 get_current_user가 서명을 검증한다.
function authHeader(token: string): { Authorization: string } {
  if (!token) {
    throw new ApiError("로그인이 필요합니다.", { statusCode: 401 });
  }
  return { Authorization: `Bearer ${token}` };
}

async function request<T>(path: string, { params, timeoutMs = 10_000, headers }: RequestOpts = {}): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    // 추천 등 데이터는 매 로드 신선해야 하므로 캐시 비활성.
    res = await fetch(url, { signal: controller.signal, cache: "no-store", headers });
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new ApiError("백엔드 응답이 늦어지고 있습니다. 잠시 후 다시 시도하세요.");
    }
    throw new ApiError("백엔드 서버에 연결할 수 없습니다.", { isConnection: true });
  } finally {
    clearTimeout(timer);
  }

  if (res.status >= 400) {
    let detail: string;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? res.statusText;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(String(detail), { statusCode: res.status });
  }
  return (await res.json()) as T;
}

export function listContent(opts: {
  source?: string;
  nodeId?: number;
  difficulty?: string;
  q?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<ContentListResponse> {
  return request<ContentListResponse>("/content", {
    params: {
      limit: opts.limit ?? 20,
      offset: opts.offset ?? 0,
      source: opts.source,
      node_id: opts.nodeId,
      difficulty: opts.difficulty,
      q: opts.q,
    },
  });
}

export function recommend(token: string, topN = 5): Promise<RecommendResponse> {
  // GraphRAG(LLM rerank)라 실측 ~12s — 타임아웃 여유 필수.
  return request<RecommendResponse>("/recommend", {
    params: { top_n: topN },
    headers: authHeader(token),
    timeoutMs: 60_000,
  });
}

// light=true면 similar_to(콘텐츠 kNN, ~26s) 계산을 건너뛴다 — 주제 노드만 필요할 때.
export function getGraph(light = false): Promise<GraphResponse> {
  return request<GraphResponse>("/graph", {
    params: light ? { light: "true" } : undefined,
    timeoutMs: light ? 12_000 : 30_000,
  });
}

export function getMastery(token: string): Promise<MasteryResponse> {
  return request<MasteryResponse>("/recommend/mastery", {
    headers: authHeader(token),
    timeoutMs: 15_000,
  });
}

// 읽은 콘텐츠 이력(읽은 순) — 학습경로 '완료' 구간용 (HIVE-65).
export function getReadHistory(token: string): Promise<ReadHistoryResponse> {
  return request<ReadHistoryResponse>("/progress", {
    headers: authHeader(token),
    timeoutMs: 15_000,
  });
}

// 유저 피드백 {content_id: feedback} — 백엔드는 Bearer JWT로 본인 식별(HIVE-100).
// 없음/오류면 빈 객체(조용히 — 신규/비로그인 정상 경로).
export async function listFeedback(token: string): Promise<Record<number, string>> {
  try {
    const data = await request<Record<string, string>>("/feedback", {
      headers: authHeader(token),
    });
    const out: Record<number, string> = {};
    for (const [k, v] of Object.entries(data ?? {})) out[Number(k)] = v;
    return out;
  } catch {
    return {};
  }
}

// 공개 프로필 조회(인증 불필요, 경로의 user_id로 조회).
export function getProfile(userId: number): Promise<Profile> {
  return request<Profile>(`/auth/profile/${userId}`);
}

export function getStats(token: string): Promise<Stats> {
  return request<Stats>("/stats", { headers: authHeader(token), timeoutMs: 15_000 });
}

export function getUserStateText(token: string): Promise<UserStateResponse> {
  return request<UserStateResponse>("/recommend/user-state", {
    headers: authHeader(token),
    timeoutMs: 15_000,
  });
}

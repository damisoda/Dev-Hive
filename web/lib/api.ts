// 백엔드 API 순수 fetch 클라이언트 — frontend/lib/api.py 의 TS 이식(1:1 변환 목표).
// 서버 컴포넌트에서만 호출(서버→백엔드 직결이라 CORS 불필요). 실패는 ApiError(한국어)로 통일.

import type { ContentListResponse, RecommendResponse } from "./types";

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
}

async function request<T>(path: string, { params, timeoutMs = 10_000 }: RequestOpts = {}): Promise<T> {
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
    res = await fetch(url, { signal: controller.signal, cache: "no-store" });
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
    },
  });
}

export function recommend(userId: number, topN = 5): Promise<RecommendResponse> {
  // GraphRAG(LLM rerank)라 실측 ~12s — 타임아웃 여유 필수.
  return request<RecommendResponse>("/recommend", {
    params: { user_id: userId, top_n: topN },
    timeoutMs: 60_000,
  });
}

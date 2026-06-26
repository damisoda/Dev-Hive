"use client";

// HIVE-64: 홈 피드 — 클라이언트 컴포넌트로 전환.
// - components['schemas']['ContentResponse'] (= ContentItem alias) 타입 바인딩.
// - useEffect 내 fetch는 { credentials: 'include' }로 백엔드 CORS + 세션 쿠키 충족.
// - 컴포넌트 마운트 시 sessionStorage user_profile 세션 유지 헬퍼 적용.

import { useEffect, useState, useCallback } from "react";
// HIVE-63/64: frontend/src/types/schema.ts 의 ContentResponse (ContentItem alias) 임포트
// @schema alias = tsconfig + webpack alias → ../frontend/src/types/schema.ts
import type { components } from "@schema/schema";

type ContentResponse = components["schemas"]["ContentItem"];

// ─── 환경 변수: 브라우저에서 직접 백엔드를 호출할 경우 NEXT_PUBLIC_ 접두사 필요 ───
// 미설정 시 개발 기본값 localhost:8000 으로 폴백.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// ─── sessionStorage 세션 유지 헬퍼 ───────────────────────────────────────────
const SESSION_KEY = "user_profile";

interface UserProfile {
  name: string;
  role: string;
}

function ensureUserProfile(): UserProfile {
  if (typeof window === "undefined") return { name: "오규원", role: "developer" };
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (raw) {
    try {
      return JSON.parse(raw) as UserProfile;
    } catch {
      /* 파싱 실패 시 기본값으로 덮어쓰기 */
    }
  }
  const defaultProfile: UserProfile = { name: "오규원", role: "developer" };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(defaultProfile));
  return defaultProfile;
}
// ─────────────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

type FeedState = "idle" | "loading" | "success" | "error";

export default function HomePage() {
  const [items, setItems] = useState<ContentResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [feedState, setFeedState] = useState<FeedState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isConnection, setIsConnection] = useState(false);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);

  // 마운트 시 sessionStorage user_profile 세션 초기화
  useEffect(() => {
    setUserProfile(ensureUserProfile());
  }, []);

  // 콘텐츠 fetch — credentials:'include'로 CORS + httpOnly 쿠키 세션 유지
  const fetchContent = useCallback(async (targetPage: number) => {
    setFeedState("loading");
    setErrorMsg(null);
    setIsConnection(false);

    const offset = (targetPage - 1) * PAGE_SIZE;
    const url = `${API_BASE}/content?limit=${PAGE_SIZE}&offset=${offset}`;

    try {
      const res = await fetch(url, {
        credentials: "include",  // CORS + 쿠키(dh_token) 전송 필수
        cache: "no-store",
      });

      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = (await res.json()) as { detail?: string };
          detail = body.detail ?? detail;
        } catch { /* no-op */ }
        throw new Error(detail);
      }

      // ContentResponse[] 타입으로 정적 바인딩
      const data = (await res.json()) as {
        items: ContentResponse[];
        total: number;
      };

      setItems(data.items);
      setTotal(data.total);
      setFeedState("success");
    } catch (e: unknown) {
      const isConn =
        e instanceof TypeError &&
        (e.message.includes("Failed to fetch") ||
          e.message.includes("NetworkError") ||
          e.message.includes("ECONNREFUSED"));
      setIsConnection(isConn);
      setErrorMsg(e instanceof Error ? e.message : "알 수 없는 오류가 발생했습니다.");
      setFeedState("error");
    }
  }, []);

  useEffect(() => {
    fetchContent(page);
  }, [fetchContent, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // 난이도 배지 색상 매핑
  const difficultyStyle = (d: string | null | undefined) => {
    if (d === "beginner" || d === "입문") return "diff-intro";
    if (d === "intermediate" || d === "중급") return "diff-mid";
    if (d === "advanced" || d === "고급") return "diff-adv";
    return "";
  };

  return (
    <section className="feed" aria-label="콘텐츠 피드">
      {/* ── 히어로 섹션 ── */}
      <section className="hero" aria-labelledby="hero-heading">
        <h1 id="hero-heading">
          경험이 곧 <em>커리큘럼</em>이 된다
        </h1>
        <p>
          velog · HN · GitHub · 직접 올린 글까지, 실전 경험이 한 곳에 모여{" "}
          <strong>GraphRAG</strong> 기반 학습 경로가 됩니다.
        </p>
        {userProfile && (
          <p className="hero-session" role="status" aria-live="polite">
            안녕하세요,{" "}
            <strong>{userProfile.name}</strong>님 ({userProfile.role})
          </p>
        )}
        <span className="deco" aria-hidden="true">🐝</span>
      </section>

      {/* ── 피드 상태별 렌더링 ── */}
      {feedState === "loading" && (
        <div className="state-view" role="status" aria-live="polite" aria-label="콘텐츠 로딩 중">
          <span className="state-emoji" aria-hidden="true">⏳</span>
          <h2 className="state-title">콘텐츠를 불러오는 중입니다…</h2>
        </div>
      )}

      {feedState === "error" && (
        <div className="state-view" role="alert" aria-label="콘텐츠 로딩 오류">
          <span className="state-emoji" aria-hidden="true">
            {isConnection ? "🔌" : "⚠️"}
          </span>
          <h2 className="state-title">콘텐츠를 불러오지 못했어요</h2>
          <p className="state-body">
            {isConnection
              ? <>
                  백엔드에 연결되지 않았습니다.{" "}
                  <code>NEXT_PUBLIC_API_BASE_URL</code>(기본 localhost:8000)과 서버 기동을 확인하세요.
                </>
              : errorMsg}
          </p>
          <button
            type="button"
            className="btn-primary"
            onClick={() => fetchContent(page)}
            aria-label="콘텐츠 다시 불러오기"
          >
            다시 시도
          </button>
        </div>
      )}

      {feedState === "success" && items.length === 0 && (
        <div className="state-view" role="status" aria-live="polite" aria-label="콘텐츠 없음">
          <span className="state-emoji" aria-hidden="true">🐝</span>
          <h2 className="state-title">피드가 비어 있어요</h2>
          <p className="state-body">크롤·업로드로 글이 쌓이면 출처별로 여기 모입니다.</p>
        </div>
      )}

      {feedState === "success" && items.length > 0 && (
        <>
          {/* 콘텐츠 카드 목록 */}
          <ul className="feed-list" aria-label="콘텐츠 목록" role="list">
            {items.map((item) => (
              <li key={item.id} className="content-card" aria-label={item.title}>
                {/* 출처 + 난이도 배지 */}
                <div className="card-meta">
                  <span className="card-source" aria-label={`출처: ${item.source}`}>
                    {item.source}
                  </span>
                  {item.difficulty && (
                    <span
                      className={`diff-badge ${difficultyStyle(item.difficulty)}`}
                      aria-label={`난이도: ${item.difficulty}`}
                    >
                      {item.difficulty}
                    </span>
                  )}
                  {item.content_type && (
                    <span className="type-badge" aria-label={`유형: ${item.content_type}`}>
                      {item.content_type}
                    </span>
                  )}
                </div>

                {/* 제목 */}
                <h2 className="card-title">
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`${item.title} (새 탭에서 열기)`}
                    >
                      {item.title}
                    </a>
                  ) : (
                    item.title
                  )}
                </h2>

                {/* 요약 */}
                {item.summary && (
                  <p className="card-summary">{item.summary}</p>
                )}

                {/* 태그 */}
                {Array.isArray(item.tags) && item.tags.length > 0 && (
                  <ul className="card-tags" aria-label="태그 목록" role="list">
                    {(item.tags as string[]).map((tag, i) => (
                      <li key={i} className="tag-chip">
                        {tag}
                      </li>
                    ))}
                  </ul>
                )}

                {/* 푸터: 작성자·날짜·품질점수 */}
                <footer className="card-footer">
                  {item.author_name && (
                    <span className="card-author" aria-label={`작성자: ${item.author_name}`}>
                      {item.author_name}
                    </span>
                  )}
                  {item.published_at && (
                    <time
                      dateTime={item.published_at}
                      className="card-date"
                      aria-label={`게시일: ${new Date(item.published_at).toLocaleDateString("ko-KR")}`}
                    >
                      {new Date(item.published_at).toLocaleDateString("ko-KR")}
                    </time>
                  )}
                  {typeof item.quality_score === "number" && (
                    <span className="card-quality" aria-label={`품질 점수: ${item.quality_score.toFixed(2)}`}>
                      ★ {item.quality_score.toFixed(2)}
                    </span>
                  )}
                </footer>
              </li>
            ))}
          </ul>

          {/* 페이지네이션 */}
          {totalPages > 1 && (
            <nav className="pagination" aria-label="페이지 이동">
              <button
                type="button"
                className="page-btn"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                aria-label="이전 페이지"
                aria-disabled={page === 1}
              >
                ‹ 이전
              </button>
              <span className="page-info" aria-current="page" aria-label={`${page} 페이지 / 전체 ${totalPages} 페이지`}>
                {page} / {totalPages}
              </span>
              <button
                type="button"
                className="page-btn"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                aria-label="다음 페이지"
                aria-disabled={page === totalPages}
              >
                다음 ›
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

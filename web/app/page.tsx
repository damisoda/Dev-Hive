// 홈 피드 — 인디고 히어로(테제) + 출처별 콘텐츠 포스트. 서버 컴포넌트에서 백엔드 직접 fetch.

import { listContent, listFeedback, ApiError } from "@/lib/api";
import type { ContentItem } from "@/lib/types";
import { ContentCard } from "@/components/ContentCard";
import { FilterBar } from "@/components/FilterBar";
import { SearchBar } from "@/components/SearchBar";
import { Pagination } from "@/components/Pagination";
import { StateView } from "@/components/StateView";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 20;

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string; difficulty?: string; q?: string; page?: string }>;
}) {
  const { source, difficulty, q, page: pageParam } = await searchParams;
  const page = Math.max(1, Number(pageParam) || 1);
  const query = q?.trim() || undefined;
  const session = await getSession();

  let items: ContentItem[] = [];
  let total = 0;
  let error: ApiError | null = null;

  try {
    const data = await listContent({
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      source,
      difficulty,
      q: query,
    });
    items = data.items;
    total = data.total;
  } catch (e) {
    error = e instanceof ApiError ? e : new ApiError("알 수 없는 오류가 발생했습니다.");
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // 로그인 시 현재 피드백 상태 1회 조회(Bearer) — 버튼 활성 표시용.
  const feedbackMap = session ? await listFeedback(session.token) : {};

  return (
    <main className="feed">
      <section className="hero">
        <h2>
          경험이 곧 <em>커리큘럼</em>이 된다
        </h2>
        <p>velog·HN·GitHub·직접 올린 글까지, 실전 경험이 한 곳에 모여 학습 경로가 됩니다.</p>
        <span className="deco" aria-hidden>
          🐝
        </span>
      </section>

      <div className="feed-controls">
        <FilterBar />
        <SearchBar />
      </div>

      {error ? (
        <StateView emoji={error.isConnection ? "🔌" : "⚠️"} title="콘텐츠를 불러오지 못했어요">
          {error.isConnection ? (
            <>
              백엔드에 연결되지 않았습니다. <code>API_BASE_URL</code>(기본 localhost:8000)과 서버
              기동을 확인하세요.
            </>
          ) : (
            error.message
          )}
        </StateView>
      ) : items.length === 0 ? (
        query ? (
          <StateView emoji="🔍" title={`‘${query}’ 검색 결과가 없어요`}>
            다른 검색어를 써보거나 필터를 풀어보세요.
          </StateView>
        ) : (
          <StateView emoji="🐝" title="피드가 비어 있어요">
            크롤·업로드로 글이 쌓이면 출처별로 여기 모입니다.
          </StateView>
        )
      ) : (
        <>
          {query && <div className="sec-sub">‘{query}’ 검색 결과 {total}건</div>}
          {items.map((item) => (
            <ContentCard
              key={item.id}
              item={item}
              loggedIn={Boolean(session)}
              feedback={feedbackMap[item.id] ?? null}
            />
          ))}
          {totalPages > 1 && <Pagination page={page} totalPages={totalPages} />}
        </>
      )}
    </main>
  );
}

// 홈 피드 — 전체 콘텐츠를 최신순으로 둘러보기('둘러보기'). 개인화 추천은 커리큘럼(후속).
// 서버 컴포넌트에서 백엔드를 직접 fetch → 브라우저 CORS 불필요.

import { listContent, ApiError } from "@/lib/api";
import type { ContentItem } from "@/lib/types";
import { ContentCard } from "@/components/ContentCard";
import { StateView } from "@/components/StateView";

export const dynamic = "force-dynamic"; // 매 요청 신선한 피드

const PAGE_SIZE = 20;

export default async function HomePage() {
  let items: ContentItem[] = [];
  let total = 0;
  let error: ApiError | null = null;

  try {
    const data = await listContent({ limit: PAGE_SIZE });
    items = data.items;
    total = data.total;
  } catch (e) {
    error = e instanceof ApiError ? e : new ApiError("알 수 없는 오류가 발생했습니다.");
  }

  return (
    <main className="container">
      <header className="page-head">
        <h1>피드</h1>
        <p>전체 콘텐츠를 최신순으로 둘러보세요. 개인화 추천은 커리큘럼에서.</p>
      </header>

      {error ? (
        <StateView emoji={error.isConnection ? "🔌" : "⚠️"} title="콘텐츠를 불러오지 못했습니다">
          {error.isConnection ? (
            <>
              백엔드 서버에 연결할 수 없습니다. <code>API_BASE_URL</code>(기본 localhost:8000)과
              백엔드 기동 상태를 확인하세요.
            </>
          ) : (
            error.message
          )}
        </StateView>
      ) : items.length === 0 ? (
        <StateView emoji="🐝" title="아직 콘텐츠가 없습니다">
          크롤·업로드로 콘텐츠가 쌓이면 여기에 피드로 나타납니다.
        </StateView>
      ) : (
        <>
          <p className="feed-count">총 {total.toLocaleString()}건</p>
          {items.map((item) => (
            <ContentCard key={item.id} item={item} />
          ))}
        </>
      )}
    </main>
  );
}

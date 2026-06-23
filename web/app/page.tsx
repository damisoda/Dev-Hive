// 홈 피드 — 인디고 히어로(테제) + 출처별 콘텐츠 포스트. 서버 컴포넌트에서 백엔드 직접 fetch.

import { listContent, ApiError } from "@/lib/api";
import type { ContentItem } from "@/lib/types";
import { ContentCard } from "@/components/ContentCard";
import { StateView } from "@/components/StateView";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 20;

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string; difficulty?: string }>;
}) {
  const { source, difficulty } = await searchParams;

  let items: ContentItem[] = [];
  let error: ApiError | null = null;

  try {
    const data = await listContent({ limit: PAGE_SIZE, source, difficulty });
    items = data.items;
  } catch (e) {
    error = e instanceof ApiError ? e : new ApiError("알 수 없는 오류가 발생했습니다.");
  }

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
        <StateView emoji="🐝" title="피드가 비어 있어요">
          크롤·업로드로 글이 쌓이면 출처별로 여기 모입니다.
        </StateView>
      ) : (
        items.map((item) => <ContentCard key={item.id} item={item} />)
      )}
    </main>
  );
}

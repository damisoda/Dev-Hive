// 디스커버 — 주제별 탐색. /graph 토픽 노드 그리드 → 선택 시 /content?node_id=로 그 주제 콘텐츠.

import { getGraph, listContent, ApiError } from "@/lib/api";
import type { ContentItem } from "@/lib/types";
import { ContentCard } from "@/components/ContentCard";
import { StateView } from "@/components/StateView";

export const dynamic = "force-dynamic";
export const metadata = {
  title: "디스커버",
  description: "관심 주제를 골라 Dev-Hive에서 분야별 경험·자료를 탐색하세요.",
};

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<{ topic?: string }>;
}) {
  const { topic } = await searchParams;

  let topics: { id: string; label: string; count: number }[] = [];
  let items: ContentItem[] = [];
  let activeLabel: string | null = null;
  let error: ApiError | null = null;

  try {
    const g = await getGraph();
    const counts: Record<string, number> = {};
    for (const e of g.edges) if (e.rel === "belongs_to") counts[e.target] = (counts[e.target] ?? 0) + 1;
    topics = g.nodes
      .filter((n) => n.kind === "topic" && !n.auto)
      .map((n) => ({ id: n.id, label: n.label, count: counts[n.id] ?? 0 }))
      .sort((a, b) => b.count - a.count);

    if (topic) {
      activeLabel = topics.find((t) => t.id === topic)?.label ?? null;
      const nid = Number(topic.includes(":") ? topic.split(":")[1] : topic);
      const data = await listContent({ nodeId: nid, limit: 20 });
      items = data.items;
    }
  } catch (e) {
    error = e instanceof ApiError ? e : new ApiError("알 수 없는 오류가 발생했습니다.");
  }

  return (
    <section className="feed" aria-label="디스커버 — 주제별 탐색">

      {/* ── 섹션 헤더 ── */}
      <header className="sec-head" role="banner">
        {/* layout.tsx의 <main>이 h1 역할을 하므로 여기서는 h2로 시작 */}
        <h2 id="discover-heading">주제별 둘러보기</h2>
        <p>
          관심 주제를 골라 그 분야의 경험·자료를 모아 보세요.
          <span className="sec-hint"> (홈은 최신, 디스커버는 주제별)</span>
        </p>
      </header>

      {error ? (
        <StateView emoji={error.isConnection ? "🔌" : "⚠️"} title="주제를 불러오지 못했어요">
          {error.isConnection ? "백엔드에 연결되지 않았습니다." : error.message}
        </StateView>
      ) : (
        <>
          {/* ── 주제 그리드 ── */}
          <section aria-labelledby="discover-heading" aria-label="주제 목록">
            <nav aria-label="주제 선택 메뉴">
              <ul className="topic-grid" role="list" aria-label="전체 주제">
                {topics.map((t) => (
                  <li key={t.id}>
                    <a
                      href={`/discover?topic=${t.id}`}
                      className={`topic-card${topic === t.id ? " active" : ""}`}
                      aria-label={`${t.label} (콘텐츠 ${t.count}개)`}
                      aria-current={topic === t.id ? "true" : undefined}
                    >
                      <span className="topic-name">{t.label}</span>
                      <span className="topic-count" aria-hidden="true">{t.count}개</span>
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </section>

          {/* ── 선택된 주제 콘텐츠 ── */}
          {topic && (
            <section aria-label={`'${activeLabel ?? "선택한 주제"}' 콘텐츠`}>
              {items.length > 0 ? (
                <>
                  <div className="sec-sub" role="status" aria-live="polite">
                    <strong>'{activeLabel ?? "선택한 주제"}'</strong> 콘텐츠{" "}
                    <span aria-label={`${items.length}건`}>{items.length}건</span>
                  </div>
                  <ul className="feed-list" role="list" aria-label={`${activeLabel ?? "선택한 주제"} 콘텐츠 목록`}>
                    {items.map((item) => (
                      <li key={item.id}>
                        <ContentCard key={item.id} item={item} />
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <StateView emoji="🐝" title="이 주제엔 아직 콘텐츠가 없어요">
                  다른 주제를 골라보거나, 직접 글을 올려 첫 콘텐츠를 채워보세요.
                </StateView>
              )}
            </section>
          )}

          {/* 주제가 선택되지 않은 초기 상태 안내 */}
          {!topic && topics.length === 0 && (
            <StateView emoji="🗂️" title="등록된 주제가 아직 없어요">
              콘텐츠가 쌓이면 Auto-HKG가 주제를 자동으로 생성합니다.
            </StateView>
          )}
        </>
      )}
    </section>
  );
}

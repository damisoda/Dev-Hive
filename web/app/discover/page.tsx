// 디스커버 — 주제별 탐색. /graph 토픽 노드 그리드 → 선택 시 /content?node_id=로 그 주제 콘텐츠.

import { getGraph, listContent, ApiError } from "@/lib/api";
import type { ContentItem } from "@/lib/types";
import { ContentCard } from "@/components/ContentCard";
import { StateView } from "@/components/StateView";

export const dynamic = "force-dynamic";
export const metadata = { title: "디스커버 · Dev-Hive" };

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
    // belongs_to는 '가장 구체적인' 노드(하위노드)를 가리키므로, 소속 대주제로 롤업해 합산한다.
    const parentOf: Record<string, string> = {};
    for (const n of g.nodes) if (n.kind === "topic") parentOf[n.id] = n.parent ?? n.id;
    const counts: Record<string, number> = {};
    for (const e of g.edges) {
      if (e.rel !== "belongs_to") continue;
      const top = parentOf[e.target] ?? e.target;
      counts[top] = (counts[top] ?? 0) + 1;
    }
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
    <main className="feed">
      <header className="sec-head">
        <h2>주제별 둘러보기</h2>
        <p>관심 주제를 골라 그 분야의 경험·자료를 모아 보세요. (홈은 최신, 디스커버는 주제별)</p>
      </header>

      {error ? (
        <StateView emoji={error.isConnection ? "🔌" : "⚠️"} title="주제를 불러오지 못했어요">
          {error.isConnection ? "백엔드에 연결되지 않았습니다." : error.message}
        </StateView>
      ) : (
        <>
          <div className="topic-grid">
            {topics.map((t) => (
              <a key={t.id} href={`/discover?topic=${t.id}`} className={`topic-card${topic === t.id ? " active" : ""}`}>
                <span className="topic-name">{t.label}</span>
                <span className="topic-count">{t.count}개</span>
              </a>
            ))}
          </div>

          {topic &&
            (items.length > 0 ? (
              <>
                <div className="sec-sub">‘{activeLabel ?? "선택한 주제"}’ 콘텐츠 {items.length}건</div>
                {items.map((item) => (
                  <ContentCard key={item.id} item={item} />
                ))}
              </>
            ) : (
              <StateView emoji="🐝" title="이 주제엔 아직 콘텐츠가 없어요">
                다른 주제를 골라보거나, 직접 글을 올려 첫 콘텐츠를 채워보세요.
              </StateView>
            ))}
        </>
      )}
    </main>
  );
}

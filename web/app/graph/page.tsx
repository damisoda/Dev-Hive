// 지식그래프 — /graph 실데이터를 인터랙티브 포스그래프로. 서버에서 fetch(브라우저 CORS 회피) 후 클라 캔버스에 주입.

import { getGraph, ApiError } from "@/lib/api";
import { GraphCanvas } from "@/components/GraphCanvas";
import { StateView } from "@/components/StateView";

export const dynamic = "force-dynamic";
export const metadata = { title: "지식그래프 · Dev-Hive" };

export default async function GraphPage() {
  try {
    const data = await getGraph();
    // similar_to(콘텐츠-콘텐츠)는 1200+라 헤어볼 → 강한 연결(≥0.65)만, belongs_to/precedes는 전부 유지.
    const edges = data.edges.filter((e) => e.rel !== "similar_to" || e.weight >= 0.65);
    const s = data.stats;

    return (
      <main className="graph-page">
        <div className="graph-head">
          <div>
            <h2>지식그래프</h2>
            <p>
              주제 {s.topics} · 콘텐츠 {s.content} · 유사연결 {s.similar_to?.toLocaleString?.() ?? s.similar_to}
            </p>
          </div>
          <div className="legend">
            <span className="lg"><i style={{ background: "#4E68C7" }} />대주제</span>
            <span className="lg"><i style={{ background: "#A9B4E0" }} />자동 하위노드</span>
            <span className="lg"><i style={{ background: "#CBD0DA" }} />콘텐츠</span>
          </div>
        </div>
        <GraphCanvas data={{ ...data, edges }} />
        <p className="graph-foot">노드를 드래그·줌하며 탐색하세요. 콘텐츠는 소속 주제 주변으로 모입니다.</p>
      </main>
    );
  } catch (e) {
    const err = e instanceof ApiError ? e : new ApiError("알 수 없는 오류가 발생했습니다.");
    return (
      <main className="feed coming">
        <StateView emoji={err.isConnection ? "🔌" : "⚠️"} title="지식그래프를 불러오지 못했어요">
          {err.isConnection ? "백엔드에 연결되지 않았습니다. 서버 기동을 확인하세요." : err.message}
        </StateView>
      </main>
    );
  }
}

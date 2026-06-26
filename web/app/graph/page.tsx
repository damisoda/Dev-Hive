// 지식그래프 — /graph 실데이터를 인터랙티브 포스그래프로. 서버에서 fetch(브라우저 CORS 회피) 후 클라 캔버스에 주입.

import { getGraph, getMastery, ApiError } from "@/lib/api";
import { GraphCanvas, type GraphHighlight } from "@/components/GraphCanvas";
import { StateView } from "@/components/StateView";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata = { title: "지식그래프 · Dev-Hive" };

type SearchParamValue = string | string[] | undefined;
type SearchParams = Record<string, SearchParamValue>;

function firstParam(value: SearchParamValue) {
  return Array.isArray(value) ? value[0] : value;
}

function graphNodeId(value: SearchParamValue, fallbackKind?: "content" | "topic") {
  const raw = firstParam(value);
  if (!raw) return undefined;
  if (/^(content|topic):\d+$/.test(raw)) return raw;
  if (fallbackKind && /^\d+$/.test(raw)) return `${fallbackKind}:${raw}`;
  return undefined;
}

function graphHighlight(params: SearchParams): GraphHighlight | undefined {
  const contentId = graphNodeId(params.content, "content");
  const topicId = graphNodeId(params.topic, "topic");
  const focusId = graphNodeId(params.focus) ?? topicId ?? contentId;
  if (!focusId && !contentId && !topicId) return undefined;
  return {
    focusId,
    contentId,
    topicId,
    isNew: firstParam(params.new) === "1",
  };
}

export default async function GraphPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const [highlight, session] = await Promise.all([
    searchParams ? searchParams.then(graphHighlight) : Promise.resolve(undefined),
    getSession(),
  ]);

  // 로그인 유저의 학습 경로 노드: mastery > 0 인 topic nodeId 집합
  let pathIds: string[] = [];
  if (session?.token) {
    try {
      const m = await getMastery(session.token);
      pathIds = Object.entries(m.mastery)
        .filter(([, v]) => v > 0)
        .map(([k]) => k);
    } catch {
      // mastery 실패 시 조용히 무시 — 그래프는 계속 렌더됨
    }
  }

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
        <GraphCanvas data={{ ...data, edges }} highlight={highlight} loggedIn={!!session} pathIds={pathIds} />
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

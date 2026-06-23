// 커리큘럼 — 학습경로. /recommend/mastery + /graph 토픽으로 주제별 숙련도 단계(약한 개념 먼저).
// auth 전까지 current user는 유저 6(조대흠) 고정 — 붙으면 세션 유저로 교체.

import { getGraph, getMastery, ApiError } from "@/lib/api";
import { curriculumRows } from "@/lib/viewmodel";
import { StateView } from "@/components/StateView";

export const dynamic = "force-dynamic";
export const metadata = { title: "커리큘럼 · Dev-Hive" };

const CURRENT_USER_ID = 6; // 임시(조대흠). auth 붙으면 세션 유저로 교체.

export default async function CurriculumPage() {
  try {
    const [g, m] = await Promise.all([getGraph(), getMastery(CURRENT_USER_ID)]);
    const topics = g.nodes
      .filter((n) => n.kind === "topic" && !n.auto)
      .map((n) => ({ id: n.id, label: n.label }));
    const rows = curriculumRows(topics, m.mastery);

    return (
      <main className="feed">
        <header className="sec-head">
          <h2>학습 경로</h2>
          <p>주제별 숙련도예요. 약한 개념부터 채워 나가면 경험이 곧 커리큘럼이 됩니다.</p>
        </header>

        <div className="curriculum">
          {rows.map((r) => (
            <div key={r.id} className="cur-row">
              <div className="cur-top">
                <span className="cur-name">{r.name}</span>
                {r.next && <span className="cur-badge">다음 추천 학습</span>}
                <span className="cur-stage">{r.label}</span>
              </div>
              <div className="cur-bar">
                <span className="cur-fill" style={{ width: `${Math.round(r.m * 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
        <p className="sec-foot">
          숙련도는 읽기·피드백 활동으로 올라갑니다. <a href="/">홈에서 둘러보기 →</a>
        </p>
      </main>
    );
  } catch (e) {
    const err = e instanceof ApiError ? e : new ApiError("알 수 없는 오류가 발생했습니다.");
    return (
      <main className="feed coming">
        <StateView emoji={err.isConnection ? "🔌" : "⚠️"} title="학습 경로를 불러오지 못했어요">
          {err.isConnection ? "백엔드에 연결되지 않았습니다." : err.message}
        </StateView>
      </main>
    );
  }
}

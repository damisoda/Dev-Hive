// 커리큘럼 — 학습경로. /recommend/mastery + /graph 토픽으로 주제별 숙련도 단계(약한 개념 먼저).
// current user = 세션 유저(회원가입 시 발급, dh_uid 쿠키). 비로그인은 시작하기 CTA.

import { getGraph, getMastery, ApiError } from "@/lib/api";
import { curriculumRows } from "@/lib/viewmodel";
import { StateView } from "@/components/StateView";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata = { title: "커리큘럼 · Dev-Hive" };

export default async function CurriculumPage() {
  const session = await getSession();
  if (!session) {
    return (
      <main className="feed coming">
        <StateView emoji="🐝" title="학습 경로를 보려면 시작하세요">
          <a href="/onboarding" style={{ color: "var(--accent-ink)", fontWeight: 600 }}>시작하기 →</a>{" "}
          닉네임과 지금 수준만 알려주면 바로 만들어집니다.
        </StateView>
      </main>
    );
  }

  try {
    const [g, m] = await Promise.all([getGraph(), getMastery(session.userId)]);
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

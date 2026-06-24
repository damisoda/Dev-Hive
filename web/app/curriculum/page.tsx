// 커리큘럼 — 학습경로. /recommend/mastery + /graph 토픽으로 주제별 숙련도 단계(약한 개념 먼저).
// current user = 세션 유저(회원가입 시 발급, dh_uid 쿠키). 비로그인은 시작하기 CTA.

import { Suspense } from "react";
import { getGraph, getMastery, recommend, ApiError } from "@/lib/api";
import { curriculumRows } from "@/lib/viewmodel";
import { StateView } from "@/components/StateView";
import { RecommendationCard } from "@/components/RecommendationCard";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata = { title: "커리큘럼 · Dev-Hive" };

// 추천(GraphRAG ~12s)은 Suspense로 분리 — 학습경로 먼저 렌더, 추천은 뒤따라 스트리밍.
async function Recommendations({ userId }: { userId: number }) {
  try {
    const data = await recommend(userId, 5);
    if (data.recommendations.length === 0) {
      return <p className="sec-foot">아직 추천할 자료가 없어요. 글을 읽거나 피드백을 남기면 채워집니다.</p>;
    }
    return (
      <div className="rec-list">
        {data.recommendations.map((r, i) => (
          <RecommendationCard key={r.content_id} rec={r} rank={i + 1} />
        ))}
      </div>
    );
  } catch {
    return <p className="sec-foot">추천을 불러오지 못했어요. 잠시 후 새로고침해 주세요.</p>;
  }
}

function RecsSkeleton() {
  return (
    <div className="rec-list">
      {[0, 1, 2].map((i) => (
        <div key={i} className="rec-card rec-skeleton" aria-hidden>
          <div className="rec-rank">·</div>
          <div className="rec-body">
            <div className="skel-line w40" />
            <div className="skel-line w80" />
          </div>
        </div>
      ))}
    </div>
  );
}

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
        <h3 className="sec-sub">다음 학습 자료</h3>
        <Suspense fallback={<RecsSkeleton />}>
          <Recommendations userId={session.userId} />
        </Suspense>

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

// 커리큘럼 — 학습 경로(콘텐츠 단계) + 다음 학습 자료(상세 카드) + 주제별 숙련도.
// 학습 경로 = 읽은 자료(완료) + 추천 자료(예정)를 순서대로 이은 경로(HIVE-65).
// current user = 세션 유저(회원가입 시 발급, dh_uid 쿠키). 비로그인은 시작하기 CTA.

import { Suspense } from "react";
import { getGraph, getMastery, getReadHistory, recommend, listFeedback, ApiError } from "@/lib/api";
import { curriculumRows, contentPath } from "@/lib/viewmodel";
import { StateView } from "@/components/StateView";
import { RecommendationCard } from "@/components/RecommendationCard";
import { ReadLink } from "@/components/ReadLink";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata = { title: "커리큘럼 · Dev-Hive" };

// 학습 경로 + 다음 학습 자료 — 둘 다 추천(recommend, GraphRAG ~12s)을 쓰므로 한 번만 호출해 같이 렌더.
async function PathAndRecs({ token }: { token: string }) {
  try {
    const [readRes, recRes, feedbackMap] = await Promise.all([
      getReadHistory(token),
      recommend(token, 5),
      listFeedback(token),
    ]);
    const path = contentPath(readRes.items, recRes.recommendations);
    const recs = recRes.recommendations;
    const loggedIn = true; // 이 섹션은 세션 게이트 뒤에서만 렌더 → 항상 로그인 상태

    return (
      <>
        {/* ── 학습 경로 ── */}
        {path.steps.length === 0 ? (
          <p className="sec-foot">아직 경로를 만들 자료가 없어요. 글을 읽거나 추천을 받아보세요.</p>
        ) : (
          <>
            <div className="path-head">
              <div className="path-prog">
                <span className="path-fill" style={{ width: `${Math.round(path.progress * 100)}%` }} />
              </div>
              <p className="path-next">
                전체 진행도 {Math.round(path.progress * 100)}%
                {path.currentTitle
                  ? <> · 다음 차례 <strong>{path.currentTitle}</strong></>
                  : <> · 🎉 추천 자료를 다 읽었어요</>}
              </p>
            </div>
            {path.prevReadCount > 0 && (
              <p className="path-prev">··· 이전에 읽은 자료 {path.prevReadCount}개</p>
            )}
            <ol className="path-list">
              {path.steps.map((s) => (
                <li key={s.content_id} className={`path-step is-${s.status}`}>
                  <span className="path-node" aria-hidden>
                    <span className="path-dot">{s.status === "done" ? "✓" : ""}</span>
                  </span>
                  <div className="path-body">
                    <div className="path-row">
                      {s.status === "done" ? (
                        // 이미 읽음 — 원문 링크만(재로깅 불필요)
                        s.url ? (
                          <a className="path-name" href={s.url} target="_blank" rel="noopener noreferrer">
                            {s.title}
                          </a>
                        ) : (
                          <span className="path-name">{s.title}</span>
                        )
                      ) : (
                        // 예정/현위치 — 클릭 시 읽음 처리하며 원문 열기(HIVE-97)
                        <ReadLink className="path-name" contentId={s.content_id} url={s.url} loggedIn={loggedIn}>
                          {s.title}
                        </ReadLink>
                      )}
                      {s.status === "current" && <span className="path-here">다음 차례</span>}
                    </div>
                    <div className="path-meta">
                      {s.status === "done" ? "완료" : s.status === "current" ? "학습 중" : "예정"}
                      {s.topic ? <> · {s.topic}</> : null}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </>
        )}

        {/* ── 다음 학습 자료 (상세 카드) ── */}
        <h3 className="sec-sub-soft">다음 학습 자료</h3>
        {recs.length === 0 ? (
          <p className="sec-foot">아직 추천할 자료가 없어요. 글을 읽거나 피드백을 남기면 채워집니다.</p>
        ) : (
          <div className="rec-list">
            {recs.map((r, i) => (
              <RecommendationCard key={r.content_id} rec={r} rank={i + 1} loggedIn={loggedIn} feedback={feedbackMap[r.content_id] ?? null} />
            ))}
          </div>
        )}
      </>
    );
  } catch (e) {
    const err = e instanceof ApiError ? e : new ApiError("알 수 없는 오류가 발생했습니다.");
    return (
      <p className="sec-foot">
        {err.isConnection ? "백엔드에 연결되지 않았습니다." : "학습 경로를 불러오지 못했어요. 잠시 후 새로고침해 주세요."}
      </p>
    );
  }
}

// 주제별 숙련도 — /graph(주제 노드) + /mastery. /graph가 느려 별도 Suspense로 뒤늦게 스트리밍.
async function MasterySection({ token }: { token: string }) {
  try {
    const [g, m] = await Promise.all([getGraph(true), getMastery(token)]);
    const topics = g.nodes
      .filter((n) => n.kind === "topic" && !n.auto)
      .map((n) => ({ id: n.id, label: n.label }));
    const rows = curriculumRows(topics, m.mastery);
    return (
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
    );
  } catch {
    return <p className="sec-foot">주제별 숙련도를 불러오지 못했어요.</p>;
  }
}

function PathSkeleton() {
  return (
    <div className="path-head">
      <div className="path-prog">
        <span className="path-fill" style={{ width: "15%" }} />
      </div>
      <p className="path-next">학습 경로 불러오는 중…</p>
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

  return (
    <main className="feed">
      <header className="sec-head">
        <h2>학습 경로</h2>
        <p>읽은 자료와 다음에 읽을 자료를 순서대로 이어 보여줘요. 지금 어디까지 왔는지 한눈에.</p>
      </header>

      <Suspense fallback={<PathSkeleton />}>
        <PathAndRecs token={session.token} />
      </Suspense>

      <h3 className="sec-sub sec-sub-lg">주제별 숙련도</h3>
      <p className="sec-note">약한 개념부터 채워 나가면 경험이 곧 커리큘럼이 됩니다.</p>
      <Suspense fallback={<p className="sec-foot">주제별 숙련도 불러오는 중…</p>}>
        <MasterySection token={session.token} />
      </Suspense>

      <p className="sec-foot">
        숙련도는 읽기·피드백 활동으로 올라갑니다. <a href="/">홈에서 둘러보기 →</a>
      </p>
    </main>
  );
}

// 프로필 — 신원 블록 + 스탯 3개 + 학습 활동(벌집 히트맵) + 주제별 진행 현황.
// 비로그인은 시작하기 게이트.

import { Suspense } from "react";
import { getProfile, getStats, getGraph, getReadHistory } from "@/lib/api";
import type { Profile, Stats } from "@/lib/types";
import { levelMedalColor, topicProgressRows } from "@/lib/viewmodel";
import { Heatmap } from "@/components/Heatmap";
import { StateView } from "@/components/StateView";
import { InfoTip } from "@/components/InfoTip";
import { getSession } from "@/lib/session";

export const metadata = { title: "프로필 · Dev-Hive" };
export const dynamic = "force-dynamic";

const TOPIC_CELLS = 10;

// 메달 아이콘(배경 칩 없이 색만 — spec). 레벨별 색은 levelMedalColor.
function Medal({ level }: { level: string }) {
  return (
    <svg
      viewBox="0 0 24 24" fill="none" stroke={levelMedalColor(level)} strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" width={17} height={17} aria-hidden
    >
      <path d="M8.5 3.5 7 9l5 2 5-2-1.5-5.5" />
      <circle cx="12" cy="15.5" r="5" />
      <path d="M12 13.2l0.9 1.9 2 .3-1.5 1.4.4 2-1.8-1-1.8 1 .4-2-1.5-1.4 2-.3z" fill={levelMedalColor(level)} stroke="none" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" width={15} height={15} aria-hidden>
      <path d="M4 20h4l10-10-4-4L4 16z" />
      <path d="M13.5 6.5 17.5 10.5" />
    </svg>
  );
}

// 주제별 진행 현황 — /graph(주제·belongs_to) + /progress(읽음). graph가 느려 별도 스트리밍.
async function TopicSection({ token }: { token: string }) {
  try {
    const [g, readRes] = await Promise.all([getGraph(true), getReadHistory(token)]);
    const topics = g.nodes
      .filter((n) => n.kind === "topic")
      .map((n) => ({ id: n.id, label: n.label, parent: n.parent ?? null, auto: n.auto }));
    const rows = topicProgressRows(topics, readRes.items);

    if (rows.length === 0) {
      return <p className="sec-foot" style={{ marginTop: 0 }}>주제 정보를 불러오지 못했어요.</p>;
    }

    return (
      <div className="topic-prog">
        {rows.map((r) => (
          <div className="tp-row" key={r.id}>
            <span className="tp-name">{r.name}</span>
            <span className="tp-cells" aria-hidden>
              {r.cells.map((t, i) => (
                <span key={i} className={`tp-hex t${t}`} />
              ))}
            </span>
            <span className="tp-status">{r.status}</span>
          </div>
        ))}
      </div>
    );
  } catch {
    return <p className="sec-foot" style={{ marginTop: 0 }}>주제별 진행 현황을 불러오지 못했어요.</p>;
  }
}

function TopicSkeleton() {
  return (
    <div className="topic-prog">
      {Array.from({ length: 7 }).map((_, i) => (
        <div className="tp-row" key={i}>
          <span className="tp-name skeleton sk-line" style={{ width: 120 }} />
          <span className="tp-cells" aria-hidden>
            {Array.from({ length: TOPIC_CELLS }).map((_, j) => (
              <span key={j} className="tp-hex" />
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

export default async function ProfilePage() {
  const session = await getSession();
  if (!session) {
    return (
      <main className="feed coming">
        <StateView emoji="🐝" title="프로필을 보려면 시작하세요">
          <a href="/onboarding" style={{ color: "var(--accent-ink)", fontWeight: 600 }}>
            시작하기 →
          </a>{" "}
          닉네임만 정하면 학습 현황이 쌓입니다.
        </StateView>
      </main>
    );
  }

  // 일부 실패(예: 통계)해도 나머지는 보여준다.
  const [profileR, statsR] = await Promise.allSettled([
    getProfile(session.userId),
    getStats(session.token),
  ]);
  const profile: Profile | null = profileR.status === "fulfilled" ? profileR.value : null;
  const stats: Stats | null = statsR.status === "fulfilled" ? statsR.value : null;

  const name = profile?.display_name ?? session.displayName ?? "프로필";
  const persona = profile?.persona ?? "개발자";
  const level = profile?.current_level ?? "입문";
  const initial = name.trim().slice(0, 1) || "🐝";

  const readTotal = stats ? Object.values(stats.heatmap).reduce((a, b) => a + b, 0) : 0;
  const streak = stats?.streak ?? 0;
  const influence = stats?.influence_score ?? 0;

  return (
    <main className="feed">
      {/* ① 신원 블록 */}
      <section className="ident">
        <div className="ident-avatar" aria-hidden>{initial}</div>
        <div className="ident-body">
          <h2 className="ident-name">{name}</h2>
          <div className="ident-meta">
            <span className="ident-persona">{persona}</span>
            <button type="button" className="ident-change">변경</button>
            <span className="ident-dot">·</span>
            <span className="ident-level">{level}</span>
            <Medal level={level} />
          </div>
        </div>
        <a href="/profile/edit" className="ident-edit">
          <EditIcon /> 정보 수정
        </a>
      </section>

      {/* ② 스탯 3개 — 박스 없이 파란 세로 구분선 + 가운데 정렬 */}
      <div className="pstat-row">
        <div className="pstat">
          <div className="pstat-value">{streak}일</div>
          <div className="pstat-label">연속 학습</div>
        </div>
        <div className="pstat">
          <div className="pstat-value">{readTotal}</div>
          <div className="pstat-label">
            읽은 글 <InfoTip text="최근 1년간 읽은 글 수예요" />
          </div>
        </div>
        <div className="pstat">
          <div className="pstat-value">{influence}</div>
          <div className="pstat-label">영향력 점수</div>
        </div>
      </div>

      {/* ③ 학습 활동 — 벌집(육각) 히트맵 */}
      <h3 className="sec-sub psec">
        학습 활동 <InfoTip text="최근 14주 · 진할수록 그날 많이 읽음" />
      </h3>
      {stats && readTotal > 0 ? (
        <div className="hivemap-wrap">
          <Heatmap data={stats.heatmap} />
        </div>
      ) : (
        <p className="sec-foot" style={{ marginTop: 0 }}>
          콘텐츠를 읽으면 여기에 학습 기록이 채워집니다. <a href="/">홈에서 둘러보기 →</a>
        </p>
      )}

      {/* ④ 주제별 진행 현황 — 항상 펼침 */}
      <h3 className="sec-sub psec">
        주제별 진행 현황 <InfoTip text="커리큘럼 7대 주제 · 읽은 콘텐츠" />
      </h3>
      <Suspense fallback={<TopicSkeleton />}>
        <TopicSection token={session.token} />
      </Suspense>
    </main>
  );
}

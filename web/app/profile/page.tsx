// 프로필 — 카드형 대시보드. 헤로(신원+레벨) · 스탯 3 · 학습 활동(히트맵+요약) · 주제별 숙련도(클릭→읽은 글).
// 영향력은 '점수'로만 표시(티어 미구현). 점수 산출 근거는 툴팁으로.
import { Suspense } from "react";
import { getProfile, getStats, getGraph, getReadHistory } from "@/lib/api";
import type { Profile, Stats } from "@/lib/types";
import { levelMedalColor, topicProgressRows } from "@/lib/viewmodel";
import { Heatmap } from "@/components/Heatmap";
import { StateView } from "@/components/StateView";
import { InfoTip } from "@/components/InfoTip";
import { TopicMastery, type TopicArticle } from "@/components/TopicMastery";
import { getSession } from "@/lib/session";

export const metadata = { title: "프로필 · Dev-Hive" };
export const dynamic = "force-dynamic";

const TOPIC_CELLS = 10;
const WN = ["일", "월", "화", "수", "목", "금", "토"];

function Medal({ level }: { level: string }) {
  const c = levelMedalColor(level);
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" width={16} height={16} aria-hidden>
      <path d="M8.5 3.5 7 9l5 2 5-2-1.5-5.5" />
      <circle cx="12" cy="15.5" r="5" />
      <path d="M12 13.2l0.9 1.9 2 .3-1.5 1.4.4 2-1.8-1-1.8 1 .4-2-1.5-1.4 2-.3z" fill={c} stroke="none" />
    </svg>
  );
}
function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" width={15} height={15} aria-hidden>
      <path d="M4 20h4l10-10-4-4L4 16z" /><path d="M13.5 6.5 17.5 10.5" />
    </svg>
  );
}
const IconFlame = () => (
  <svg viewBox="0 0 24 24" width={22} height={22} fill="#D49C3A" aria-hidden>
    <path d="M12.5 2.5C13.2 6.4 16.8 7.6 15.7 12.4 16.9 11.8 17.4 10.6 17.5 9.4 19.2 11.2 20 13.4 20 15.3 20 19 16.4 21.6 12 21.6 7.2 21.6 4 18.7 4 14.7 4 12.2 5.5 9.6 7.4 8.2 7.3 9.6 7.8 10.6 8.7 11 8.1 7.4 10.6 5.2 12.5 2.5Z" />
  </svg>
);
const IconBookmark = () => (
  <svg viewBox="0 0 24 24" width={22} height={22} fill="none" stroke="#C68A2B" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M6 3.5H15.5A2 2 0 0 1 17.5 5.5V20.5L11.7 17.2 6 20.5Z" />
  </svg>
);
const IconSpark = () => (
  <svg viewBox="0 0 24 24" width={22} height={22} fill="#4E68C7" aria-hidden>
    <path d="M12 2.6 13.7 9 20.2 10.6 13.7 12.2 12 18.8 10.3 12.2 3.8 10.6 10.3 9Z" />
  </svg>
);

// 히트맵 요약: 최장 연속 · 학습한 날 · 가장 활발한 요일 (현재 연속은 stats.streak).
function heatSummary(heatmap: Record<string, number>): { longest: number; active: number; topW: string } {
  const active = Object.values(heatmap).filter((c) => c > 0).length;
  const dates = Object.keys(heatmap).sort();
  let longest = 0, run = 0;
  const lit = new Set(dates.filter((d) => heatmap[d] > 0));
  if (dates.length) {
    for (let d = new Date(dates[0]); d <= new Date(dates[dates.length - 1]); d.setDate(d.getDate() + 1)) {
      const k = d.toISOString().slice(0, 10);
      if (lit.has(k)) { run++; if (run > longest) longest = run; } else run = 0;
    }
  }
  const w = [0, 0, 0, 0, 0, 0, 0];
  for (const d of dates) if (heatmap[d] > 0) w[new Date(d).getDay()] += heatmap[d];
  let tw = 0;
  for (let i = 1; i < 7; i++) if (w[i] > w[tw]) tw = i;
  return { longest, active, topW: active > 0 ? `${WN[tw]}요일` : "—" };
}

async function TopicSection({ token }: { token: string }) {
  try {
    const [g, readRes] = await Promise.all([getGraph(true), getReadHistory(token)]);
    const topics = g.nodes
      .filter((n) => n.kind === "topic")
      .map((n) => ({ id: n.id, label: n.label, parent: n.parent ?? null, auto: n.auto }));
    const rows = topicProgressRows(topics, readRes.items);
    if (rows.length === 0) return <p className="sec-foot" style={{ marginTop: 0 }}>주제 정보를 불러오지 못했어요.</p>;

    // 읽은 글을 대주제별로 묶는다(최신 먼저) — 주제 클릭 시 펼쳐 보여줄 목록.
    const articlesByTopic: Record<string, TopicArticle[]> = {};
    for (const it of readRes.items) {
      if (!it.topic) continue;
      (articlesByTopic[it.topic] ??= []).push({ content_id: it.content_id, title: it.title, url: it.url ?? null });
    }
    for (const k of Object.keys(articlesByTopic)) articlesByTopic[k].reverse();

    return <TopicMastery rows={rows} articlesByTopic={articlesByTopic} loggedIn />;
  } catch {
    return <p className="sec-foot" style={{ marginTop: 0 }}>주제별 진행 현황을 불러오지 못했어요.</p>;
  }
}

function TopicSkeleton() {
  return (
    <div className="pf-topic-grid">
      {Array.from({ length: 6 }).map((_, i) => (
        <div className="pf-topic-card" key={i}>
          <div className="pf-topic-head">
            <span className="pf-topic-name skeleton sk-line" style={{ width: 120 }} />
          </div>
          <span className="pf-topic-cells" aria-hidden>
            {Array.from({ length: TOPIC_CELLS }).map((_, j) => <span key={j} className="tp-hex" />)}
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
          <a href="/onboarding" style={{ color: "var(--accent-ink)", fontWeight: 600 }}>시작하기 →</a>{" "}
          닉네임만 정하면 학습 현황이 쌓입니다.
        </StateView>
      </main>
    );
  }

  const [profileR, statsR] = await Promise.allSettled([getProfile(session.userId), getStats(session.token)]);
  const profile: Profile | null = profileR.status === "fulfilled" ? profileR.value : null;
  const stats: Stats | null = statsR.status === "fulfilled" ? statsR.value : null;

  const name = profile?.display_name ?? session.displayName ?? "프로필";
  const persona = profile?.persona ?? "개발자";
  const level = profile?.current_level ?? "입문";
  const initial = name.trim().slice(0, 1) || "🐝";

  const readTotal = stats ? Object.values(stats.heatmap).reduce((a, b) => a + b, 0) : 0;
  const streak = stats?.streak ?? 0;
  const influence = stats?.influence_score ?? 0;
  const sum = stats ? heatSummary(stats.heatmap) : { longest: 0, active: 0, topW: "—" };

  return (
    <main className="feed pf">
      {/* ① 헤로 — 신원 + 레벨/메달 */}
      <section className="pf-card pf-hero">
        <div className="pf-hex-avatar" aria-hidden>{initial}</div>
        <div className="pf-hero-body">
          <div className="pf-hero-top">
            <h2 className="pf-name">{name}</h2>
            <span className="pf-level-chip"><Medal level={level} /> {level}</span>
          </div>
          <div className="pf-hero-meta">
            <span className="pf-persona">{persona}</span>
            <button type="button" className="pf-persona-edit">페르소나 변경</button>
          </div>
        </div>
        <a href="/profile/edit" className="pf-edit"><EditIcon /> 정보 수정</a>
      </section>

      {/* ② 스탯 3 카드 */}
      <section className="pf-stat-row">
        <div className="pf-stat-card">
          <div className="pf-stat-icon honey"><IconFlame /></div>
          <div>
            <div className="pf-stat-value">{streak}<span className="pf-stat-unit">일</span></div>
            <div className="pf-stat-label">연속 학습</div>
            <div className="pf-stat-sub">매일 이어서 학습 중</div>
          </div>
        </div>
        <div className="pf-stat-card">
          <div className="pf-stat-icon honey"><IconBookmark /></div>
          <div>
            <div className="pf-stat-value">{readTotal}<span className="pf-stat-unit">개</span></div>
            <div className="pf-stat-label">읽은 글 <InfoTip text="최근 1년간 읽은 글 수예요" /></div>
            <div className="pf-stat-sub">누적 학습한 콘텐츠</div>
          </div>
        </div>
        <div className="pf-stat-card">
          <div className="pf-stat-icon indigo"><IconSpark /></div>
          <div>
            <div className="pf-stat-value">{influence}</div>
            <div className="pf-stat-label">영향력 점수 <InfoTip text="읽은 글 수·난이도·연속 학습·기여로 산출돼요" /></div>
            <div className="pf-stat-sub">학습·기여 활동의 합</div>
          </div>
        </div>
      </section>

      {/* ③ 학습 활동 — 히트맵 + 요약 */}
      <section className="pf-card">
        <div className="pf-sec-head">
          <h3>학습 활동 <InfoTip text="최근 8개월 · 진할수록 그날 많이 읽음" /></h3>
          <span className="pf-sec-note">최근 8개월 · 하루에 읽은 양</span>
        </div>
        {stats && readTotal > 0 ? (
          <div className="pf-heat">
            <div className="hivemap-wrap"><Heatmap data={stats.heatmap} /></div>
            <div className="pf-heat-summary">
              <div className="pf-sumrow"><span>현재 연속</span><strong className="honey">{streak}일</strong></div>
              <div className="pf-sumrow"><span>최장 연속</span><strong>{sum.longest}일</strong></div>
              <div className="pf-sumrow"><span>학습한 날</span><strong>{sum.active}일</strong></div>
              <div className="pf-sumrow"><span>가장 활발</span><strong>{sum.topW}</strong></div>
            </div>
          </div>
        ) : (
          <p className="sec-foot" style={{ marginTop: 0 }}>
            콘텐츠를 읽으면 여기에 학습 기록이 채워집니다. <a href="/">홈에서 둘러보기 →</a>
          </p>
        )}
      </section>

      {/* ④ 주제별 숙련도 — 클릭 시 읽은 글 펼침 */}
      <section className="pf-card">
        <div className="pf-sec-head">
          <h3>주제별 숙련도 <InfoTip text="7대 주제 · 읽은 수 기준. 주제를 누르면 읽은 글이 펼쳐져요" /></h3>
          <span className="pf-sec-note">주제를 누르면 읽은 글 보기</span>
        </div>
        <Suspense fallback={<TopicSkeleton />}>
          <TopicSection token={session.token} />
        </Suspense>
      </section>
    </main>
  );
}

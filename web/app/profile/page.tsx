// 프로필 — 레벨·영향력·연속학습·학습 잔디·학습 현황(자연어). 비로그인은 시작하기 게이트.

import { getProfile, getStats, getUserStateText } from "@/lib/api";
import type { Profile, Stats, UserStateResponse } from "@/lib/types";
import { Heatmap } from "@/components/Heatmap";
import { StateView } from "@/components/StateView";
import { getSession } from "@/lib/session";

export const metadata = { title: "프로필 · Dev-Hive" };
export const dynamic = "force-dynamic";

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
  const [profileR, statsR, stateR] = await Promise.allSettled([
    getProfile(session.userId),
    getStats(session.token),
    getUserStateText(session.token),
  ]);
  const profile: Profile | null = profileR.status === "fulfilled" ? profileR.value : null;
  const stats: Stats | null = statsR.status === "fulfilled" ? statsR.value : null;
  const state: UserStateResponse | null = stateR.status === "fulfilled" ? stateR.value : null;

  const readTotal = stats ? Object.values(stats.heatmap).reduce((a, b) => a + b, 0) : 0;
  const cards = [
    { label: "현재 레벨", value: profile?.current_level ?? "입문" },
    { label: "영향력 점수", value: stats?.influence_score ?? 0 },
    { label: "읽은 글 (최근 1년)", value: readTotal },
    { label: "연속 학습", value: `${stats?.streak ?? 0}일` },
  ];

  return (
    <main className="feed">
      <header className="sec-head">
        <h2>{profile?.display_name ?? session.displayName ?? "프로필"}</h2>
        <p>{profile?.persona ?? "개발자"} · 읽기·기여 활동으로 레벨과 영향력이 올라갑니다.</p>
      </header>

      <div className="stat-grid">
        {cards.map((c) => (
          <div className="stat-card" key={c.label}>
            <div className="stat-value">{c.value}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
      </div>

      <h3 className="sec-sub">학습 잔디</h3>
      {stats && readTotal > 0 ? (
        <Heatmap data={stats.heatmap} />
      ) : (
        <p className="sec-foot" style={{ marginTop: 0 }}>
          콘텐츠를 읽으면 여기에 학습 기록이 채워집니다. <a href="/">홈에서 둘러보기 →</a>
        </p>
      )}

      <h3 className="sec-sub">내 학습 현황</h3>
      {state?.user_state ? (
        <p className="user-state">{state.user_state}</p>
      ) : (
        <p className="sec-foot" style={{ marginTop: 0 }}>
          콘텐츠를 읽으면 레벨·관심 분야·읽음 이력이 여기에 정리됩니다.
        </p>
      )}
    </main>
  );
}

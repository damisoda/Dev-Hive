import Link from "next/link";
import { redirect } from "next/navigation";

import { getSession } from "@/lib/session";

export const metadata = { title: "환영합니다 · Dev-Hive" };
export const dynamic = "force-dynamic";

const S = (p: { children: React.ReactNode }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    {p.children}
  </svg>
);

const Compass = () => <S><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></S>;
const Curriculum = () => <S><path d="m12 4 9 4-9 4-9-4z" /><path d="M5 10v5c0 1.5 3.1 3 7 3s7-1.5 7-3v-5" /></S>;
const Graph = () => <S><circle cx="6" cy="7" r="2.1" /><circle cx="18" cy="6" r="2.1" /><circle cx="15" cy="18" r="2.1" /><path d="m8 7.6 8-1M7.4 8.8 13.6 16" /></S>;

const STEPS = [
  { Icon: Compass, title: "디스커버", desc: "맞춤 콘텐츠를 탐색해 보세요." },
  { Icon: Curriculum, title: "커리큘럼", desc: "단계별 학습 경로를 확인해 보세요." },
  { Icon: Graph, title: "지식그래프", desc: "모든 콘텐츠를 하나의 그래프에서 확인해 보세요." },
];

export default async function WelcomePage() {
  const session = await getSession();
  // 가입 직후에만 의미 있는 페이지. 비로그인은 시작하기로.
  if (!session) redirect("/onboarding");

  const name = session.displayName?.trim() || "개발자";

  return (
    <main className="feed welcome-page">
      <section className="welcome">
        <div className="welcome-badge" aria-hidden>
          <svg viewBox="0 0 44 38" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 3H31L42 19 31 35H13L2 19z" strokeWidth="2.7" />
            <path d="M16 19.5l4.5 4.5 8.5-10" strokeWidth="2.8" />
          </svg>
        </div>

        <h1 className="welcome-title">환영합니다, {name} 님</h1>
        <p className="welcome-sub">
          맞춤 콘텐츠 추천으로
          <br />
          나만의 학습을 시작해 보세요.
        </p>

        <ul className="welcome-steps">
          {STEPS.map(({ Icon, title, desc }) => (
            <li key={title} className="welcome-step">
              <span className="welcome-step-icon" aria-hidden><Icon /></span>
              <span className="welcome-step-text">
                <strong>{title}</strong>
                <span>{desc}</span>
              </span>
            </li>
          ))}
        </ul>

        <div className="welcome-actions">
          <Link href="/" className="ob-submit welcome-cta">둘러보기 시작</Link>
          <Link href="/profile" className="profile-edit-cancel">내 프로필 보기</Link>
        </div>
        <p className="ob-note">입력한 정보는 프로필 &gt; 정보 수정에서 변경 가능합니다.</p>
      </section>
    </main>
  );
}

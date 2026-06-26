import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { getSession } from "@/lib/session";

export const metadata: Metadata = {
  title: {
    default: "Dev-Hive",
    template: "%s · Dev-Hive",
  },
  description: "경험이 곧 커리큘럼 — GraphRAG 기반 자가복제형 기술 커뮤니티",
  keywords: ["개발", "커리큘럼", "GraphRAG", "기술학습", "Dev-Hive"],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();

  return (
    <html lang="ko">
      <head>
        {/* Pretendard 웹폰트(동적 서브셋) — WCAG AA 가독성 기준 준수 */}
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css"
        />
      </head>
      <body>
        {/* ── 전역 앱 셸 ── */}
        <div className="app-shell-v2">

          {/* ── 고정 상단 헤더 네비게이션 바 ── */}
          <header className="topnav" role="banner">
            <nav className="topnav-inner" aria-label="주요 메뉴">
              {/* 브랜드 로고 */}
              <Link href="/" className="topnav-brand" aria-label="Dev-Hive 홈으로">
                <span className="topnav-brand-icon" aria-hidden="true">
                  {/* 벌집 헥사곤 SVG 인라인 마크 */}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true" focusable="false">
                    <path d="M7 3.5h10l5 8.5-5 8.5H7l-5-8.5z" />
                    <path d="M12 8.2 15.2 10v3.8L12 15.6 8.8 13.8V10z" fill="currentColor" stroke="none" />
                  </svg>
                </span>
                <span className="topnav-brand-name">Dev-Hive</span>
              </Link>

              {/* ── 2라우트 메인 네비게이션 링크 ── */}
              <ul className="topnav-links" role="list">
                <li>
                  <Link href="/" className="topnav-link" aria-label="홈 피드">
                    홈
                  </Link>
                </li>
                <li>
                  <Link href="/discover" className="topnav-link" aria-label="주제별 디스커버">
                    디스커버
                  </Link>
                </li>
              </ul>

              {/* ── 우측 세션 영역 ── */}
              <div className="topnav-session" aria-label="사용자 메뉴">
                {session ? (
                  <>
                    <span className="topnav-avatar" title={session.displayName ?? "내 프로필"} aria-label={`프로필: ${session.displayName ?? "사용자"}`}>
                      {session.displayName?.trim()?.[0] ?? "·"}
                    </span>
                    <Link href="/profile" className="topnav-link" aria-label="내 프로필 보기">
                      {session.displayName ?? "프로필"}
                    </Link>
                  </>
                ) : (
                  <Link href="/onboarding" className="topnav-cta" aria-label="Dev-Hive 시작하기">
                    시작하기
                  </Link>
                )}
              </div>
            </nav>
          </header>

          {/* ── 페이지 콘텐츠 영역 ── */}
          <main id="main-content" tabIndex={-1} aria-label="페이지 본문">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

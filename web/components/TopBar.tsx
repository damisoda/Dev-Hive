"use client";

import { usePathname } from "next/navigation";
import type { Session } from "@/lib/session";

// 탑바 — 좌측 섹션 타이틀 + 우측 세션(아바타+로그아웃) 또는 시작하기.
const TITLES: Record<string, string> = {
  "/": "홈",
  "/discover": "디스커버",
  "/curriculum": "커리큘럼",
  "/graph": "지식그래프",
  "/profile": "프로필",
  "/upload": "업로드",
  "/onboarding": "시작하기",
};

export function TopBar({ session }: { session: Session | null }) {
  const path = usePathname();
  const title = TITLES[path] ?? "Dev-Hive";

  async function logout() {
    await fetch("/api/auth/profile", { method: "DELETE" });
    window.location.href = "/";
  }

  const initial = session?.displayName?.trim()?.[0] ?? "·";

  return (
    <header className="topbar">
      <h1>{title}</h1>
      <div className="topbar-right">
        {session ? (
          <>
            <span className="avatar" title={session.displayName ?? "내 프로필"}>
              {initial}
            </span>
            <button type="button" className="link-btn" onClick={logout}>
              로그아웃
            </button>
          </>
        ) : (
          <a className="topbar-cta" href="/onboarding">
            시작하기
          </a>
        )}
      </div>
    </header>
  );
}

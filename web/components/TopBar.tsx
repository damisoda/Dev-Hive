"use client";

import { usePathname } from "next/navigation";

// 탑바 — 좌측 섹션 타이틀 + 우측 유저 아바타. RocketPunch 홈처럼 최소.
const TITLES: Record<string, string> = {
  "/": "홈",
  "/discover": "디스커버",
  "/curriculum": "커리큘럼",
  "/graph": "지식그래프",
  "/profile": "프로필",
  "/upload": "업로드",
};

export function TopBar() {
  const path = usePathname();
  const title = TITLES[path] ?? "Dev-Hive";
  return (
    <header className="topbar">
      <h1>{title}</h1>
      <span className="avatar" aria-label="내 프로필" title="조대흠">
        조
      </span>
    </header>
  );
}

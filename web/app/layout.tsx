import type { Metadata } from "next";
import "./globals.css";
import { LeftRail } from "@/components/LeftRail";
import { TopBar } from "@/components/TopBar";
import { getSession } from "@/lib/session";

export const metadata: Metadata = {
  title: "Dev-Hive",
  description: "경험이 곧 커리큘럼 — 자가복제형 기술 커뮤니티",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();
  return (
    <html lang="ko">
      <head>
        {/* Pretendard 웹폰트(동적 서브셋) */}
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css"
        />
      </head>
      <body>
        <div className="app-shell">
          <LeftRail />
          <div className="app-main">
            <TopBar session={session} />
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}

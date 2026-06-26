"use client";

// 전역 에러 경계 (HIVE-94) — 루트 레이아웃 자체가 터졌을 때만 동작(이 경우 레일·탑바도 못 그림).
// 루트 레이아웃을 대체하므로 html/body를 직접 렌더해야 한다. globals.css를 다시 불러 톤 유지.

import "./globals.css";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[global-error]", error);
  }, [error]);

  return (
    <html lang="ko">
      <body>
        <main className="feed coming">
          <div className="state">
            <span className="emoji">🐝</span>
            <h2>잠시 문제가 생겼어요</h2>
            <p>페이지를 새로 불러오면 대부분 해결됩니다.</p>
          </div>
          <div className="state-actions">
            <button type="button" className="btn-retry" onClick={reset}>
              다시 시도
            </button>
            <a href="/" className="btn-ghost">
              홈으로
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}

"use client";

// 라우트 에러 경계 공용 UI (HIVE-94). 각 error.tsx에서 얇게 재사용한다.
// 클라이언트 컴포넌트(GraphCanvas·Heatmap 등)의 렌더 예외를 해당 페이지 영역에 가두고,
// 좌측 레일·탑바(루트 레이아웃)는 살린 채 '다시 시도'(reset)로 그 세그먼트만 재마운트한다.

import { useEffect } from "react";
import { StateView } from "@/components/StateView";

export function RouteError({
  error,
  reset,
  title = "문제가 생겼어요",
  children,
}: {
  error: Error & { digest?: string };
  reset: () => void;
  title?: string;
  children?: React.ReactNode;
}) {
  useEffect(() => {
    // 운영 로깅 훅 자리. digest로 서버 로그와 대조 가능.
    console.error("[route-error]", error);
  }, [error]);

  return (
    <main className="feed coming">
      <StateView emoji="⚠️" title={title}>
        {children ?? "일시적인 문제일 수 있어요. 다시 시도하거나 잠시 후 들러주세요."}
      </StateView>
      <div className="state-actions">
        <button type="button" className="btn-retry" onClick={reset}>
          다시 시도
        </button>
        <a href="/" className="btn-ghost">
          홈으로
        </a>
      </div>
    </main>
  );
}

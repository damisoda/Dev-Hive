"use client";

// 지식그래프 에러 경계 (HIVE-94) — GraphCanvas(포스그래프/캔버스) 렌더 예외를 이 페이지에 가둔다.
// 서버 fetch 실패는 page.tsx가 이미 StateView로 처리하므로, 여기는 클라 렌더 폭발 담당.

import { RouteError } from "@/components/RouteError";

export default function GraphError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteError {...props} title="지식그래프를 표시할 수 없어요">
      그래프를 그리는 중 문제가 생겼어요. 다시 시도하거나 잠시 후 들러주세요.
    </RouteError>
  );
}

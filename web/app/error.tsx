"use client";

// 루트 에러 경계 (HIVE-94) — 하위 모든 라우트의 렌더 예외를 받아 루트 레이아웃(레일·탑바)
// 안쪽 콘텐츠 영역에만 가둔다. 세그먼트별 error.tsx가 있으면 그쪽이 우선.

import { RouteError } from "@/components/RouteError";

export default function Error(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} />;
}

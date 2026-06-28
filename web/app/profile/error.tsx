"use client";

// 프로필 에러 경계 (HIVE-94) — Heatmap(학습 잔디) 렌더 예외를 이 페이지에 가둔다.
// 통계 fetch 일부 실패는 page.tsx가 allSettled로 흡수하므로, 여기는 클라 렌더 폭발 담당.

import { RouteError } from "@/components/RouteError";

export default function ProfileError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteError {...props} title="프로필을 표시할 수 없어요">
      학습 현황을 그리는 중 문제가 생겼어요. 다시 시도하거나 잠시 후 들러주세요.
    </RouteError>
  );
}

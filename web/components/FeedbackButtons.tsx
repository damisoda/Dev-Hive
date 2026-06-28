"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { FEEDBACK_BUTTONS } from "@/lib/viewmodel";

// 각 버튼이 추천에 어떻게 작용하는지 설명하는 툴팁(커스텀 CSS, data-tip 속성).
const TOOLTIPS: Record<string, string> = {
  understood: "이 토픽의 이해도를 올려 더 심화된 글을 추천해요. (이 글은 추천에서 제외)",
  too_hard: "이 토픽을 더 쉬운 기초 자료 위주로 다시 추천해요.",
  want_more: "이 글과 비슷한 글의 추천 가중치를 실시간으로 높여요.",
  not_interested: "이 글을 추천에서 빼고 새 추천을 불러와요.",
};

// 콘텐츠 피드백 4종 토글. 같은 버튼 재클릭 = 해제(DELETE). BFF(/api/feedback)로만 호출.
export function FeedbackButtons({ contentId, current }: { contentId: number; current: string | null }) {
  const router = useRouter();
  const [value, setValue] = useState<string | null>(current);
  const [busy, setBusy] = useState(false);

  // 서버 새로고침으로 current가 바뀌면 로컬 상태 동기화.
  useEffect(() => {
    setValue(current);
  }, [current]);

  async function toggle(key: string) {
    if (busy) return;
    const active = value === key;
    const prev = value;
    setBusy(true);
    setValue(active ? null : key); // 낙관적 업데이트
    try {
      const res = await fetch("/api/feedback", {
        method: active ? "DELETE" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(active ? { content_id: contentId } : { content_id: contentId, feedback: key }),
      });
      if (!res.ok) {
        setValue(prev); // 롤백
      } else {
        router.refresh(); // 서버 상태 동기화(추천 반영 등)
      }
    } catch {
      setValue(prev);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fb-row" role="group" aria-label="이 콘텐츠 피드백">
      {FEEDBACK_BUTTONS.map((b) => (
        <button
          key={b.key}
          type="button"
          data-tip={TOOLTIPS[b.key]}
          aria-label={`${b.label} — ${TOOLTIPS[b.key]}`}
          className={`fb-btn${value === b.key ? " active" : ""}`}
          onClick={() => toggle(b.key)}
          disabled={busy}
          aria-pressed={value === b.key}
        >
          {value === b.key ? "✓ " : ""}
          {b.label}
        </button>
      ))}
    </div>
  );
}

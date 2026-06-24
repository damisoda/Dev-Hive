"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FEEDBACK_BUTTONS } from "@/lib/viewmodel";

// 콘텐츠 피드백 4종 토글. 같은 버튼 재클릭 = 해제(DELETE). BFF(/api/feedback)로만 호출.
export function FeedbackButtons({ contentId, current }: { contentId: number; current: string | null }) {
  const router = useRouter();
  const [value, setValue] = useState<string | null>(current);
  const [busy, setBusy] = useState(false);

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

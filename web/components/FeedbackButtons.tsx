"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

interface FeedbackButtonsProps {
  content_id: string;
  value: string | null;
  userName?: string;
}

function getTooltipText(key: string, displayName: string): string {
  switch (key) {
    case "understood":
      return "이해했어요: 이 토픽의 이해도를 높여 더 심화된 콘텐츠를 추천합니다. (현재 추천 풀에선 제외)";
    case "too_hard":
      return "어려워요: 이 토픽의 난이도를 하향 조정하여 더 쉬운 기초 자료 위주로 커리큘럼을 다시 구성합니다.";
    case "want_more":
      return "더 보고 싶어요: 이 자료와 유사한 핵심 키워드를 분석하여 AI 추천 가중치를 실시간으로 높입니다.";
    case "not_interested":
      return `관심없어요: 해당 콘텐츠를 추천 풀에서 영구 제외하고 ${displayName}님의 새 추천 라인업을 불러옵니다.`;
    default:
      return "";
  }
}

const BUTTONS = [
  { key: "understood",    label: "이해했어요" },
  { key: "too_hard",      label: "어려워요" },
  { key: "want_more",     label: "더 보고 싶어요" },
  { key: "not_interested", label: "관심없어요" },
];

export default function FeedbackButtons({ content_id, value, userName }: FeedbackButtonsProps) {
  const router = useRouter();
  const [currentValue, setCurrentValue] = useState<string | null>(value);
  const [busy, setBusy] = useState(false);
  const displayName = userName?.trim() || "회원";

  useEffect(() => {
    setCurrentValue(value);
  }, [value]);

  async function toggle(key: string) {
    if (busy) return;
    const active = currentValue === key;
    const prev = currentValue;
    setBusy(true);
    setCurrentValue(active ? null : key);
    try {
      const res = await fetch("/api/feedback", {
        method: active ? "DELETE" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(active ? { content_id } : { content_id, feedback: key }),
      });
      if (!res.ok) setCurrentValue(prev);
      else router.refresh();
    } catch {
      setCurrentValue(prev);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fb-row" role="group" aria-label="이 콘텐츠 피드백">
      {BUTTONS.map((btn) => (
        <button
          key={btn.key}
          type="button"
          title={getTooltipText(btn.key, displayName)}
          className={`fb-btn${currentValue === btn.key ? " active" : ""}`}
          onClick={() => toggle(btn.key)}
          disabled={busy}
          aria-pressed={currentValue === btn.key}
        >
          {currentValue === btn.key ? "✓ " : ""}
          {btn.label}
        </button>
      ))}
    </div>
  );
}

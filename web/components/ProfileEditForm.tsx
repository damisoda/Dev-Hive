"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ONBOARDING_QUESTIONS, defaultOnboardingAnswers } from "@/lib/onboardingQuestions";
import type { EditableProfile } from "@/lib/types";

export function ProfileEditForm({ profile }: { profile: EditableProfile }) {
  const router = useRouter();
  const initialAnswers = useMemo(
    () => ({ ...defaultOnboardingAnswers(), ...(profile.onboarding_answers ?? {}) }),
    [profile.onboarding_answers]
  );
  const [name, setName] = useState(profile.display_name);
  const [answers, setAnswers] = useState<Record<string, number>>(initialAnswers);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const displayName = name.trim();
    if (!displayName) {
      setError("닉네임을 입력해 주세요.");
      return;
    }

    setBusy(true);
    try {
      const res = await fetch("/api/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: displayName,
          persona: profile.persona || "개발자",
          onboarding_answers: answers,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error ?? "프로필 저장에 실패했습니다.");
        setBusy(false);
        return;
      }
      router.refresh();
      router.push("/profile");
    } catch {
      setError("네트워크 오류가 발생했습니다.");
      setBusy(false);
    }
  }

  return (
    <form className="onboard profile-edit" onSubmit={submit}>
      <div className="ob-field">
        <label htmlFor="profile-name">닉네임</label>
        <input
          id="profile-name"
          className="ob-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="피드에 표시될 이름"
          maxLength={100}
          autoFocus
        />
      </div>

      {ONBOARDING_QUESTIONS.map((q) => (
        <div key={q.key} className="ob-field">
          <label>{q.label}</label>
          <div className="ob-options">
            {q.options.map((opt, i) => (
              <button
                type="button"
                key={i}
                className={`ob-opt${answers[q.key] === i ? " active" : ""}`}
                onClick={() => setAnswers((a) => ({ ...a, [q.key]: i }))}
                aria-pressed={answers[q.key] === i}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      ))}

      {error && <p className="ob-error">{error}</p>}

      <div className="profile-edit-actions">
        <button type="submit" className="ob-submit" disabled={busy}>
          {busy ? "저장하는 중…" : "저장하기"}
        </button>
        <button type="button" className="profile-edit-cancel" onClick={() => router.push("/profile")}>
          취소
        </button>
      </div>
      <p className="ob-note">저장하면 현재 레벨과 추천 기준이 새 답변으로 다시 맞춰져요.</p>
    </form>
  );
}

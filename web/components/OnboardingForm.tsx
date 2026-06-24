"use client";

import { useState } from "react";

// 온보딩 = 회원가입. 답변 키/점수는 백엔드 constants.PERSONA_ONBOARDING["개발자"]와 일치해야 함.
// dev_career 0~3, 나머지 0~2 → compute_initial_level + build_initial_vector(profile_vector 시드).
const QUESTIONS: { key: string; label: string; options: string[] }[] = [
  { key: "dev_career", label: "개발 경력", options: ["학생·입문 (1년 미만)", "주니어 (1~2년)", "미들 (3~5년)", "시니어 (6년+)"] },
  { key: "prod_experience", label: "프로덕션 운영 경험", options: ["거의 없음", "일부 참여", "직접 설계·운영"] },
  { key: "ai_tool_usage", label: "AI 툴(코파일럿·ChatGPT 등) 사용", options: ["거의 안 씀", "가끔", "매일 활용"] },
  { key: "llm_understanding", label: "LLM 이해도", options: ["개념 정도", "API로 앱 만들어봄", "내부 원리·튜닝까지"] },
  { key: "advanced_topics", label: "RAG·에이전트 등 고급 주제", options: ["잘 모름", "들어봤다", "직접 구현해봤다"] },
];

export function OnboardingForm() {
  const [name, setName] = useState("");
  const [answers, setAnswers] = useState<Record<string, number>>(
    Object.fromEntries(QUESTIONS.map((q) => [q.key, 0]))
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("닉네임을 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: name.trim(), persona: "개발자", onboarding_answers: answers }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.error ?? "가입에 실패했습니다.");
        setBusy(false);
        return;
      }
      window.location.href = "/"; // 쿠키 반영된 채로 홈 재진입
    } catch {
      setError("네트워크 오류가 발생했습니다.");
      setBusy(false);
    }
  }

  return (
    <form className="onboard" onSubmit={submit}>
      <div className="ob-field">
        <label htmlFor="ob-name">닉네임</label>
        <input
          id="ob-name"
          className="ob-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="피드에 표시될 이름"
          maxLength={100}
          autoFocus
        />
      </div>

      {QUESTIONS.map((q) => (
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

      <button type="submit" className="ob-submit" disabled={busy}>
        {busy ? "시작하는 중…" : "시작하기"}
      </button>
      <p className="ob-note">답변은 초기 학습 수준과 추천을 맞추는 데만 쓰여요. 비밀번호는 받지 않습니다.</p>
    </form>
  );
}

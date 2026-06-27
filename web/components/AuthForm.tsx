"use client";

import { useState } from "react";
import { ONBOARDING_QUESTIONS, defaultOnboardingAnswers } from "@/lib/onboardingQuestions";

// HIVE-100: 가입/로그인 통합 폼. 회원가입 탭 = 아이디·비번 + 온보딩 설문(닉네임/5문항),
// 로그인 탭 = 아이디·비번만. 답변 키/점수는 백엔드 PERSONA_ONBOARDING["개발자"]와 일치.

type Mode = "signup" | "login";

export function AuthForm() {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [answers, setAnswers] = useState<Record<string, number>>(
    defaultOnboardingAnswers()
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function switchMode(m: Mode) {
    setMode(m);
    setError(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (username.trim().length < 3) {
      setError("아이디는 영문·숫자 3자 이상이어야 해요.");
      return;
    }
    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 해요.");
      return;
    }
    if (mode === "signup" && !name.trim()) {
      setError("닉네임을 입력해 주세요.");
      return;
    }

    setBusy(true);
    const endpoint = mode === "signup" ? "/api/auth/signup" : "/api/auth/login";
    const payload =
      mode === "signup"
        ? {
            username: username.trim(),
            password,
            display_name: name.trim(),
            persona: "개발자",
            onboarding_answers: answers,
          }
        : { username: username.trim(), password };
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.error ?? (mode === "signup" ? "가입에 실패했습니다." : "로그인에 실패했습니다."));
        setBusy(false);
        return;
      }
      // 가입은 환영 페이지, 로그인은 홈으로 (둘 다 쿠키 반영된 채 재진입)
      window.location.href = mode === "signup" ? "/welcome" : "/";
    } catch {
      setError("네트워크 오류가 발생했습니다.");
      setBusy(false);
    }
  }

  return (
    <form className="onboard" onSubmit={submit}>
      <div className="ob-field">
        <div className="ob-options">
          <button
            type="button"
            className={`ob-opt${mode === "signup" ? " active" : ""}`}
            onClick={() => switchMode("signup")}
            aria-pressed={mode === "signup"}
          >
            회원가입
          </button>
          <button
            type="button"
            className={`ob-opt${mode === "login" ? " active" : ""}`}
            onClick={() => switchMode("login")}
            aria-pressed={mode === "login"}
          >
            로그인
          </button>
        </div>
      </div>

      <div className="ob-field">
        <label htmlFor="au-username">아이디</label>
        <input
          id="au-username"
          className="ob-input"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="영문·숫자 3~50자"
          maxLength={50}
          autoComplete="username"
          autoFocus
        />
      </div>

      <div className="ob-field">
        <label htmlFor="au-password">비밀번호</label>
        <input
          id="au-password"
          type="password"
          className="ob-input"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="8자 이상"
          maxLength={72}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
        />
      </div>

      {mode === "signup" && (
        <>
          <div className="ob-field">
            <label htmlFor="au-name">닉네임</label>
            <input
              id="au-name"
              className="ob-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="피드에 표시될 이름"
              maxLength={100}
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
        </>
      )}

      {error && <p className="ob-error">{error}</p>}

      <button type="submit" className="ob-submit" disabled={busy}>
        {busy
          ? mode === "signup"
            ? "가입하는 중…"
            : "로그인 중…"
          : mode === "signup"
            ? "가입하고 시작하기"
            : "로그인"}
      </button>
      <p className="ob-note">
        {mode === "signup"
          ? "설문 답변은 초기 학습 수준·추천을 맞추는 데만 쓰여요."
          : "처음이신가요? 위 ‘회원가입’ 탭에서 시작하세요."}
      </p>
    </form>
  );
}

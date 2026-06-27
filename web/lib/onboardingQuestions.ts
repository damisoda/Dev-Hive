export const ONBOARDING_QUESTIONS: { key: string; label: string; options: string[] }[] = [
  { key: "dev_career", label: "개발 경력", options: ["학생·입문 (1년 미만)", "주니어 (1~2년)", "미들 (3~5년)", "시니어 (6년+)"] },
  { key: "prod_experience", label: "프로덕션 운영 경험", options: ["거의 없음", "일부 참여", "직접 설계·운영"] },
  { key: "ai_tool_usage", label: "AI 툴(코파일럿·ChatGPT 등) 사용", options: ["거의 안 씀", "가끔", "매일 활용"] },
  { key: "llm_understanding", label: "LLM 이해도", options: ["개념 정도", "API로 앱 만들어봄", "내부 원리·튜닝까지"] },
  { key: "advanced_topics", label: "RAG·에이전트 등 고급 주제", options: ["잘 모름", "들어봤다", "직접 구현해봤다"] },
];

export function defaultOnboardingAnswers(): Record<string, number> {
  return Object.fromEntries(ONBOARDING_QUESTIONS.map((q) => [q.key, 0]));
}

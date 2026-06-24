// 표시용 뷰모델 — frontend/lib/viewmodel.py 의 TS 이식(React/Next.js 이행 시 그대로 살아남는 층).
// UI 프레임워크 비의존: '데이터 → 표시용 구조' 변환만.

import type { ContentItem, Recommendation } from "./types";

// 피드백 버튼 (라벨, 내부 키) — 백엔드 /feedback 타입 4종과 일치(HIVE-37).
export const FEEDBACK_BUTTONS: { key: string; label: string }[] = [
  { key: "understood", label: "이해했어요" },
  { key: "too_hard", label: "어려워요" },
  { key: "want_more", label: "더 보고 싶어요" },
  { key: "not_interested", label: "관심없어요" },
];

// source 내부 값 → 표시 라벨
export const SOURCE_LABELS: Record<string, string> = {
  reddit: "Reddit",
  hn: "Hacker News",
  github_trending: "GitHub Trending",
  huggingface: "Hugging Face",
  velog: "Velog",
  tistory: "Tistory",
  x: "X (Twitter)",
  user: "사용자 업로드",
};

// source → 뱃지 이모지. 미등록 소스는 기본 📄.
export const SOURCE_EMOJI: Record<string, string> = {
  velog: "✍️",
  tistory: "📝",
  reddit: "👽",
  hn: "📰",
  github_trending: "⭐",
  huggingface: "🤗",
  x: "🐦",
  user: "🐝",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

export function sourceBadge(source: string): string {
  return `${SOURCE_EMOJI[source] ?? "📄"} ${sourceLabel(source)}`;
}

// ── 디자인 토큰: pill 색 매핑 (순수 표시 데이터) ──

export interface PillSpec {
  text: string;
  fg: string;
  bg: string;
}

// 난이도 컬러(칩) — 각 틴트 배경 위 본문 WCAG AA(≥4.5) 보정. 입문=초록 / 중급=주황 / 고급=빨강
const DIFFICULTY_COLORS: Record<string, { fg: string; bg: string }> = {
  입문: { fg: "#137A3A", bg: "#E7F6ED" }, // 4.86
  중급: { fg: "#A8530A", bg: "#FBF0DD" }, // 4.76 (#d97706→짙게 보정)
  고급: { fg: "#C81E1E", bg: "#FCE9E9" }, // 4.91
};
const PILL_NEUTRAL = { fg: "#5B616B", bg: "#EDF0F3" }; // 미지정/기타
const PILL_TYPE = { fg: "#1659C4", bg: "#EAF2FE" }; // content_type (블루 톤, 보라 폐기)
const PILL_SOURCE = { fg: "#3A3F49", bg: "#F2F4F6" }; // source 라벨(중립 슬레이트)
export const PILL_TAG = { fg: "#51555E", bg: "#F1F3F5" }; // 태그 칩(회색 중립)

// 난이도 → 좌측 4px 컬러 레일 색(시그니처). 채도 있는 원색 사용(레일은 비텍스트 보조라 칩과 분리).
// 미지정은 transparent → 레일 미표시.
export function difficultyRailColor(difficulty: string | null | undefined): string {
  const rail: Record<string, string> = { 입문: "#16A34A", 중급: "#D97706", 고급: "#DC2626" };
  return (difficulty && rail[difficulty]) || "transparent";
}

// item.tags(unknown[]) → 빈 문자열 제거한 string[] (RocketPunch식 키워드 칩 행).
export function contentTags(item: ContentItem): string[] {
  if (!Array.isArray(item.tags)) return [];
  return item.tags.map((t) => String(t).trim()).filter((t) => t.length > 0);
}

// content_type 내부 값 → 한글 라벨 (자가복제 거푸집 5타입)
export const CONTENT_TYPE_LABELS: Record<string, string> = {
  experience: "경험",
  tutorial: "튜토리얼",
  concept: "개념",
  tool: "툴",
  discussion: "토론",
  // 폐기 타입(재태깅 전 과거분)도 한글 라벨만 — 노출 깔끔하게(HIVE-61 본작업 전 임시)
  paper: "논문",
  news: "뉴스",
};

export function contentTypeLabel(ct: string): string {
  return CONTENT_TYPE_LABELS[ct] ?? ct;
}

export function difficultyPill(difficulty: string): PillSpec {
  const c = DIFFICULTY_COLORS[difficulty] ?? PILL_NEUTRAL;
  return { text: difficulty, ...c };
}

// /content 아이템 → pill 목록 (source/난이도/타입 순)
export function contentPills(item: ContentItem): PillSpec[] {
  const pills: PillSpec[] = [];
  if (item.source) pills.push({ text: sourceBadge(item.source), ...PILL_SOURCE });
  if (item.difficulty) pills.push(difficultyPill(item.difficulty));
  if (item.content_type) pills.push({ text: contentTypeLabel(item.content_type), ...PILL_TYPE });
  return pills;
}

// 카드 본문 pill — 난이도·타입만. source는 카드 eyebrow에서 별도로 보여주므로 제외(중복 노이즈 방지).
export function contentCorePills(item: ContentItem): PillSpec[] {
  const pills: PillSpec[] = [];
  if (item.difficulty) pills.push(difficultyPill(item.difficulty));
  if (item.content_type) pills.push({ text: contentTypeLabel(item.content_type), ...PILL_TYPE });
  return pills;
}

// 추천 적합도(0~1) → '매치 87%' 정수 퍼센트. 없으면 null.
export function matchPercent(score: number | null | undefined): number | null {
  if (score === null || score === undefined) return null;
  return Math.max(0, Math.min(100, Math.round(Number(score) * 100)));
}

// /content 아이템 → 카드 하단 메타 한 줄 (작성자 · 추천/댓글 · 품질)
export function contentMeta(item: ContentItem): string {
  const parts: string[] = [];
  if (item.author_name) parts.push(`by ${item.author_name}`);
  if (item.engagement_likes !== null && item.engagement_likes !== undefined) {
    parts.push(`👍 추천 ${item.engagement_likes}`);
    parts.push(`💬 댓글 ${item.engagement_comments ?? 0}`);
  }
  if (item.quality_score !== null && item.quality_score !== undefined) {
    parts.push(`품질 ${item.quality_score.toFixed(2)}`);
  }
  return parts.join(" · ");
}

// /recommend 아이템 → 추천 카드 표시 필드 정리.
export interface RecommendationView {
  content_id: number;
  title: string;
  url: string | null;
  summary: string | null;
  summary_pending: boolean; // lazy 가공 미완 → '준비 중'
  pills: PillSpec[];
  reason: string | null; // GraphRAG 근거 = 차별점
  score: number | null;
  match: number | null;
}

// mastery(0~1) → 단계 라벨.
export function masteryLabel(m: number): string {
  return m < 0.3 ? "미학습" : m < 0.7 ? "학습중" : "숙련";
}

export interface CurriculumRow {
  id: string;
  name: string;
  m: number;
  label: string;
  next: boolean; // 다음 추천 학습(약한 순 상위 2, 숙련 미만)
}

// 대주제 노드 + mastery → 학습경로 행(약한 개념 먼저). mastery 키는 노드 id 숫자 문자열(예: 'topic:3'→'3').
export function curriculumRows(
  topics: { id: string; label: string }[],
  mastery: Record<string, number>
): CurriculumRow[] {
  const rows: CurriculumRow[] = topics.map((t) => {
    const nid = t.id.includes(":") ? t.id.split(":")[1] : t.id;
    const m = Number(mastery[nid] ?? 0);
    return { id: t.id, name: t.label || "?", m, label: masteryLabel(m), next: false };
  });
  rows.sort((a, b) => a.m - b.m);
  for (const r of rows.slice(0, 2)) if (r.m < 0.7) r.next = true;
  return rows;
}

export function recommendationView(rec: Recommendation): RecommendationView {
  const pills: PillSpec[] = [];
  if (rec.difficulty) pills.push(difficultyPill(rec.difficulty));
  if (rec.content_type) pills.push({ text: contentTypeLabel(rec.content_type), ...PILL_TYPE });
  return {
    content_id: rec.content_id,
    title: rec.title,
    url: rec.url ?? null,
    summary: rec.summary ?? null,
    summary_pending: !rec.summary,
    pills,
    reason: rec.reason ?? null,
    score: rec.score ?? null,
    match: matchPercent(rec.score),
  };
}

// 표시용 뷰모델 — frontend/lib/viewmodel.py 의 TS 이식(React/Next.js 이행 시 그대로 살아남는 층).
// UI 프레임워크 비의존: '데이터 → 표시용 구조' 변환만.

import type { ContentItem, Recommendation } from "./types";

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

// 난이도 컬러: 입문=초록 / 중급=주황 / 고급=빨강
const DIFFICULTY_COLORS: Record<string, { fg: string; bg: string }> = {
  입문: { fg: "#16a34a", bg: "#e8f7ee" },
  중급: { fg: "#d97706", bg: "#fdf3e2" },
  고급: { fg: "#dc2626", bg: "#fdecec" },
};
const PILL_NEUTRAL = { fg: "#5a5e72", bg: "#eef0f6" }; // 미지정/기타
const PILL_TYPE = { fg: "#5b5bd6", bg: "#ececfb" }; // content_type
const PILL_SOURCE = { fg: "#3c3e54", bg: "#f1f2f8" }; // source

// content_type 내부 값 → 한글 라벨 (자가복제 거푸집 5타입)
export const CONTENT_TYPE_LABELS: Record<string, string> = {
  experience: "경험",
  tutorial: "튜토리얼",
  concept: "개념",
  tool: "툴",
  discussion: "토론",
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

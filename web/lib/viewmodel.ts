// 표시용 뷰모델 — frontend/lib/viewmodel.py 의 TS 이식(React/Next.js 이행 시 그대로 살아남는 층).
// UI 프레임워크 비의존: '데이터 → 표시용 구조' 변환만.

import type { ContentItem, Recommendation, ReadHistoryItem } from "./types";

// 피드백 버튼 (라벨, 내부 키) — 백엔드 /feedback 타입 4종과 일치(HIVE-37).
export const FEEDBACK_BUTTONS: { key: string; label: string }[] = [
  { key: "understood", label: "이해했어요" },
  { key: "too_hard", label: "어려워요" },
  { key: "want_more", label: "더 보고 싶어요" },
  { key: "not_interested", label: "관심없어요" },
];

// 재가공본(synthesis) 바디 키 → 한글 라벨. content_type별 키가 다르므로 전 타입 합집합.
// (synthesizer.py _BODY_SPECS와 일치)
export const SYNTH_BODY_LABELS: Record<string, string> = {
  // experience
  context: "상황", findings: "발견", pitfalls: "겪은 함정", numbers: "수치", verdict: "결론",
  // tool
  what: "무엇", when_to_use: "언제 쓰나", how: "사용법", requirements: "준비물", gotchas: "주의할 점",
  // concept
  definition: "정의", mechanism: "작동 원리", comparisons: "비교", when_matters: "왜 중요한가",
  // tutorial
  goal: "목표", steps: "단계", result: "결과물", notes: "노트",
  // discussion
  claim: "핵심 주장", arguments: "논거", counterpoints: "반론", conclusion: "결론",
};

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

// ── 프로필 리디자인 — 레벨 메달 색 + 주제별 진행 현황 ──
// 메달은 배경 칩 없이 아이콘 '색만' 레벨별로 다르게(spec). 레벨 체계는 HIVE-36(입문/중급/고급).
// 동(입문)→은(중급)→금(고급)으로, 위로 갈수록 귀금속 — 직관적 위계.
const LEVEL_MEDAL_COLORS: Record<string, string> = {
  입문: "#B97A56", // 동(bronze)
  중급: "#9AA3AF", // 은(silver)
  고급: "#D9A441", // 금(gold, 프로젝트 허니골드와 동일 계열)
};
export function levelMedalColor(level: string | null | undefined): string {
  return (level && LEVEL_MEDAL_COLORS[level]) || LEVEL_MEDAL_COLORS["입문"];
}

// 주제별 진행 현황 — 7대주제 행. 각 행 고정 10칸을 '읽은 수 오도미터'로 표현.
// 읽음이력 topic은 백엔드에서 이미 대주제명으로 롤업되어 오므로 대주제명으로만 매칭한다.
export interface TopicProgressRow {
  id: string;
  name: string;
  read: number; // 읽은 콘텐츠 수
  cells: number[]; // 길이 10, 각 칸의 강도 0~4 (CSS .t0~.t4)
  status: string; // "N건 완료" | "미학습"
}

const TOPIC_CELLS = 10;
const TOPIC_MAX_TIER = 4;

// 읽은 수 → 10칸 강도 배열(오도미터):
//   · 1읽음=1칸씩 왼쪽부터 연한 꿀색(t1)으로 채움 → 10읽음이면 10칸이 참
//   · 10읽음마다 왼쪽부터 1칸씩 '진한 꿀색(t2)'으로 올림(carry) → 100읽음이면 10칸 전부 t2
//   · 그 위(100읽음 단위)부터 다시 왼쪽부터 한 단계 더 진하게(t3→t4) 반복
// 즉 칸 = 읽은 수를 10진 누적으로 시각화. 더 많이 읽은 주제일수록 진하게.
export function topicCellTiers(read: number): number[] {
  const tens = Math.floor(read / 10); // 올림된 '십' 개수(누적 진한 칸)
  const units = read % 10; // 진행 중인 '일' (현재 채우는 연한 칸)
  const frontier = tens % 10; // 현재 sweep에서 진해진 칸 수
  const sweepBase = Math.floor(tens / 10); // 10칸 전체를 몇 바퀴 진하게 올렸는지(100읽음=1바퀴)
  return Array.from({ length: TOPIC_CELLS }, (_, i) => {
    const darkLayers = sweepBase + (i < frontier ? 1 : 0); // 이 칸에 쌓인 '십' 횟수
    if (darkLayers > 0) return Math.min(darkLayers + 1, TOPIC_MAX_TIER); // 진한 꿀색 t2~t4
    const isUnit = i >= frontier && i < frontier + units; // 진행 중 연한 칸
    return isUnit ? 1 : 0; // t1(연한 꿀색) / t0(빈칸)
  });
}

export function topicProgressRows(
  topics: { id: string; label: string; parent: string | null; auto: boolean }[],
  readItems: { topic: string | null }[]
): TopicProgressRow[] {
  // 읽음 수 — 대주제명별 집계(읽음이력 topic = 대주제명)
  const readByName = new Map<string, number>();
  for (const r of readItems) {
    if (!r.topic) continue;
    readByName.set(r.topic, (readByName.get(r.topic) ?? 0) + 1);
  }

  // 대주제(parent 없음 · Auto-HKG 아님) — 그래프 순서 유지, 7개
  return topics
    .filter((t) => t.parent === null && !t.auto)
    .map((t) => {
      const read = readByName.get(t.label) ?? 0;
      return {
        id: t.id,
        name: t.label || "?",
        read,
        cells: topicCellTiers(read),
        status: read > 0 ? `${read}건 완료` : "미학습",
      };
    });
}

// ── 학습 경로(콘텐츠 단계형) — HIVE-65 ──
// 읽은 자료(완료) + 추천 자료(예정)를 한 줄로 이어 '지나온 길 → 지금 → 앞길'을 보여준다.
// 단계 텍스트 = 콘텐츠 제목, 메타 = [상태 · 소속 주제]. 진행도 = 읽음 / (읽음 + 추천).

const PATH_DONE_LIMIT = 5; // '완료' 단계는 최근 N개만 표시(경로가 너무 길어지지 않게)

export type StepStatus = "done" | "current" | "upcoming";

export interface ContentStep {
  content_id: number;
  title: string;
  url: string | null;
  topic: string | null; // 소속 대주제
  status: StepStatus;
}

export interface ContentPath {
  steps: ContentStep[];
  progress: number; // 0~1, 읽음 / (읽음 + 추천)
  prevReadCount: number; // 표시에서 잘린 '이전에 읽은 자료' 수
  currentTitle: string | null; // '다음에 읽을 자료' 라벨용(=추천 1순위). 추천 없으면 null
}

// 읽은 이력(오래된→최근) + 추천(적합도 순) → 콘텐츠 학습 경로.
export function contentPath(
  read: ReadHistoryItem[],
  recs: Recommendation[]
): ContentPath {
  const totalRead = read.length;
  const total = totalRead + recs.length;
  const progress = total > 0 ? totalRead / total : 0;

  // 완료: 최근 N개만(오래된→최근 유지). 나머지는 개수로만.
  const shownRead = read.slice(-PATH_DONE_LIMIT);
  const doneSteps: ContentStep[] = shownRead.map((r) => ({
    content_id: r.content_id,
    title: r.title,
    url: r.url ?? null,
    topic: r.topic ?? null,
    status: "done",
  }));

  // 예정: 추천(점수 순 그대로). 첫 번째 = 현위치('다음 차례').
  const upSteps: ContentStep[] = recs.map((r, i) => ({
    content_id: r.content_id,
    title: r.title,
    url: r.url ?? null,
    topic: r.topic ?? null,
    status: i === 0 ? "current" : "upcoming",
  }));

  return {
    steps: [...doneSteps, ...upSteps],
    progress,
    prevReadCount: totalRead - shownRead.length,
    currentTitle: recs.length > 0 ? recs[0].title : null,
  };
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

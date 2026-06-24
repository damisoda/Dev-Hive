// 백엔드 응답 스키마와 1:1 (backend/app/api/content.py · recommend.py).
// 벡터 컬럼(text_embedding/graph_embedding)은 응답에서 제외되므로 여기에도 없음.

export interface ContentItem {
  id: number;
  title: string;
  url?: string | null;
  source: string;
  author_name?: string | null;
  language?: string | null;
  difficulty?: string | null;
  quality_score?: number | null;
  content_type?: string | null;
  tags: unknown[];
  engagement_likes?: number | null;
  engagement_comments?: number | null;
  published_at?: string | null;
  created_at?: string | null;
  summary?: string | null; // 캐시된 synthesis.one_liner(요약본), 미생성이면 null
}

export interface ContentListResponse {
  items: ContentItem[];
  total: number;
}

export interface Recommendation {
  content_id: number;
  title: string;
  score: number;
  reason?: string | null;
  url?: string | null;
  difficulty?: string | null;
  content_type?: string | null;
  summary?: string | null;
}

export interface RecommendResponse {
  recommendations: Recommendation[];
}

// /graph — 지식그래프
export interface GraphNode {
  id: string; // "topic:1" | "content:12" | "auto:..."
  kind: string; // topic | content | ...
  label: string;
  auto: boolean;
}
export interface GraphEdge {
  source: string;
  target: string;
  rel: string; // belongs_to | similar_to | precedes
  weight: number;
}
export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: Record<string, number>;
}

// /recommend/mastery
export interface MasteryResponse {
  user_id: number;
  mastery: Record<string, number>; // nodeId(문자열) → 0~1
}

// /auth/profile/{id}
export interface Profile {
  user_id: number;
  display_name: string;
  persona: string;
  current_level: string;
}

// /stats
export interface Stats {
  user_id: number;
  influence_score: number;
  streak: number;
  heatmap: Record<string, number>; // YYYY-MM-DD → 읽은 수
}

// /recommend/user-state
export interface UserStateResponse {
  user_id: number;
  user_state: string;
}

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

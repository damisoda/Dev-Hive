import type { ContentItem } from "@/lib/types";
import {
  SOURCE_EMOJI,
  sourceLabel,
  contentTypeLabel,
  difficultyPill,
  contentTags,
} from "@/lib/viewmodel";
import { FeedbackButtons } from "./FeedbackButtons";
import { ReadableTitle } from "./ReadableTitle";

const Upvote = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" />
    <path d="m8.5 12.5 3.5-3.5 3.5 3.5M12 9.5V16" />
  </svg>
);
const Comment = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 11.5a8 8 0 0 1-11.5 7.2L4 20l1.3-4A8 8 0 1 1 20 11.5z" />
  </svg>
);

export function ContentCard({
  item,
  loggedIn = false,
  feedback = null,
}: {
  item: ContentItem;
  loggedIn?: boolean;
  feedback?: string | null;
}) {
  const glyph = SOURCE_EMOJI[item.source] ?? "📄";
  const src = sourceLabel(item.source);
  const tags = contentTags(item).slice(0, 5);
  const hasUrl = Boolean(item.url);
  const author = item.author_name;
  const diff = item.difficulty ? difficultyPill(item.difficulty) : null;

  return (
    <article className="post" data-source={item.source}>
      <div className="post-head">
        <div className={`src-tile${item.source === "user" ? " is-user" : ""}`} aria-hidden>
          {glyph}
        </div>
        <div>
          <div className="src-name">{author || src}</div>
          <div className="src-sub">{author ? src : "출처"}</div>
        </div>
      </div>

      {(item.content_type || diff) && (
        <div className="chip-row" style={{ display: "flex", gap: "6px", alignItems: "center", marginBottom: "9px" }}>
          {item.content_type && (
            <span className="type-chip">
              <span className="spark">✦</span>
              {contentTypeLabel(item.content_type)}
            </span>
          )}
          {diff && (
            <span className="pill" style={{ color: diff.fg, background: diff.bg }}>
              {diff.text}
            </span>
          )}
        </div>
      )}

      {/* 제목 클릭 = 상세 카드(읽기 모달) 열기. 원문 이동은 아래 인게이지 행의 '원문 ↗'로 분리. */}
      <ReadableTitle
        variant="feed"
        contentId={item.id}
        title={item.title}
        url={item.url}
        loggedIn={loggedIn}
        titleKo={item.title_ko}
      />

      {item.summary && <p className="post-summary">{item.summary}</p>}

      {tags.length > 0 && (
        <div className="tag-row">
          {tags.map((t, i) => (
            <span key={i} className="tag-chip">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="engage">
        <span className="item">
          <Upvote />
          {item.engagement_likes ?? 0}
        </span>
        <span className="item">
          <Comment />
          {item.engagement_comments ?? 0}
        </span>
        {item.quality_score != null && <span className="item">품질 {item.quality_score.toFixed(2)}</span>}
        {hasUrl && (
          <a className="origin" href={item.url ?? "#"} target="_blank" rel="noopener noreferrer">
            원문 ↗
          </a>
        )}
      </div>

      {loggedIn && <FeedbackButtons contentId={item.id} current={feedback} />}
    </article>
  );
}

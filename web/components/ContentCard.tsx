import type { ContentItem } from "@/lib/types";
import { contentPills, contentMeta } from "@/lib/viewmodel";
import { PillRow } from "./Pill";

export function ContentCard({ item }: { item: ContentItem }) {
  const pills = contentPills(item);
  const meta = contentMeta(item);
  const hasUrl = Boolean(item.url);

  const titleInner = (
    <>
      {item.title}
      {hasUrl && <span className="ext">원문 ↗</span>}
    </>
  );

  return (
    <article className="card">
      {hasUrl ? (
        <a className="card-title" href={item.url ?? "#"} target="_blank" rel="noopener noreferrer">
          {titleInner}
        </a>
      ) : (
        <h2 className="card-title">{item.title}</h2>
      )}
      <PillRow pills={pills} />
      {meta && <div className="card-meta">{meta}</div>}
    </article>
  );
}

"use client";

import { useState } from "react";
import { ReadModal } from "./ReadModal";
import type { TopicProgressRow } from "@/lib/viewmodel";

export type TopicArticle = { content_id: number; title: string; url: string | null };

// 주제별 숙련도(읽은 수 기준) + 각 주제를 누르면 그 주제로 읽은 글을 펼쳐 보여준다.
// 읽은 수→레벨/진행은 표시용(실 mastery 아님). 글 제목 클릭 = 읽기 모달.
function levelName(read: number): string {
  return read <= 0 ? "미학습" : read < 5 ? "입문" : read < 10 ? "중급" : "고급";
}
function levelTier(read: number): number {
  return read <= 0 ? 0 : read < 5 ? 1 : read < 10 ? 2 : 3;
}
function barInfo(read: number): { pct: number; note: string } {
  if (read <= 0) return { pct: 0, note: "아직 학습 전" };
  if (read < 5) return { pct: read / 5, note: `중급까지 ${5 - read}건` };
  if (read < 10) return { pct: read / 10, note: `고급까지 ${10 - read}건` };
  return { pct: 1, note: "최고 단계 달성" };
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`pf-chev${open ? " open" : ""}`}
      viewBox="0 0 24 24" width={15} height={15} fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function TopicMastery({
  rows,
  articlesByTopic,
  loggedIn,
}: {
  rows: TopicProgressRow[];
  articlesByTopic: Record<string, TopicArticle[]>;
  loggedIn: boolean;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="pf-topic-grid">
      {rows.map((r) => {
        const arts = articlesByTopic[r.name] ?? [];
        const isOpen = openId === r.id;
        const tier = levelTier(r.read);
        const bi = barInfo(r.read);
        const canOpen = arts.length > 0;
        return (
          <div className={`pf-topic-card${isOpen ? " open" : ""}`} key={r.id}>
            <button
              type="button"
              className="pf-topic-head"
              onClick={() => canOpen && setOpenId(isOpen ? null : r.id)}
              aria-expanded={isOpen}
              data-static={canOpen ? undefined : "1"}
            >
              <span className="pf-topic-name">{r.name}</span>
              <span className={`pf-topic-chip lv${tier}`}>{levelName(r.read)}</span>
              <span className={`pf-topic-count${r.read > 0 ? " on" : ""}`}>
                {r.read > 0 ? `${r.read}건` : "미학습"}
              </span>
              {canOpen && <Chevron open={isOpen} />}
            </button>

            <span className="pf-topic-cells" aria-hidden>
              {r.cells.map((t, i) => (
                <span key={i} className={`tp-hex t${t}`} />
              ))}
            </span>

            <div className="pf-topic-barrow">
              <div className="pf-bar-track">
                <div className={`pf-bar${r.read > 0 ? "" : " empty"}`} style={{ width: `${Math.round(bi.pct * 100)}%` }} />
              </div>
              <span className="pf-bar-note">{bi.note}</span>
            </div>

            {isOpen && (
              <div className="pf-topic-articles">
                {arts.map((a) => (
                  <ReadModal
                    key={a.content_id}
                    contentId={a.content_id}
                    title={a.title}
                    url={a.url}
                    loggedIn={loggedIn}
                    renderTrigger={(open) => (
                      <button type="button" className="pf-article" onClick={open}>
                        <span className="pf-article-dot" aria-hidden />
                        <span className="pf-article-title">{a.title}</span>
                      </button>
                    )}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

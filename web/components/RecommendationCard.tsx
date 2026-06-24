import type { Recommendation } from "@/lib/types";
import { recommendationView } from "@/lib/viewmodel";

// 커리큘럼 '다음 학습 자료' — /recommend(GraphRAG) 한 건. 순위·매치%·pill·요약·근거.
export function RecommendationCard({ rec, rank }: { rec: Recommendation; rank: number }) {
  const vm = recommendationView(rec);
  return (
    <article className="rec-card">
      <div className="rec-rank">{rank}</div>
      <div className="rec-body">
        <div className="rec-meta">
          {vm.match != null && <span className="rec-match">매치 {vm.match}%</span>}
          {vm.pills.map((p, i) => (
            <span key={i} className="pill" style={{ color: p.fg, background: p.bg }}>
              {p.text}
            </span>
          ))}
        </div>
        {vm.url ? (
          <a className="rec-title" href={vm.url} target="_blank" rel="noopener noreferrer">
            {vm.title}
            <span className="ext">원문 ↗</span>
          </a>
        ) : (
          <h3 className="rec-title">{vm.title}</h3>
        )}
        {vm.summary ? (
          <p className="rec-summary">{vm.summary}</p>
        ) : (
          vm.summary_pending && <p className="rec-pending">AI 요약 준비 중 — 잠시 후 새로고침하면 표시됩니다.</p>
        )}
        {vm.reason && <blockquote className="rec-reason">{vm.reason}</blockquote>}
      </div>
    </article>
  );
}

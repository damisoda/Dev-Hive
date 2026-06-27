import type { Recommendation } from "@/lib/types";
import { recommendationView } from "@/lib/viewmodel";
import { ReadModal } from "./ReadModal";
import { FeedbackButtons } from "./FeedbackButtons";

// 커리큘럼 '다음 학습 자료' — /recommend(GraphRAG) 한 건. 순위·매치%·pill·요약·근거.
// 읽기(ReadModal) 시 읽음 처리되어 학습 경로 '완료'로 반영된다 (HIVE-97).
// 피드백(이해/어려움/더보기/관심없음)도 홈 피드와 동일하게 남길 수 있다(추천 개인화 반영).
export function RecommendationCard({
  rec,
  rank,
  loggedIn = false,
  feedback = null,
}: {
  rec: Recommendation;
  rank: number;
  loggedIn?: boolean;
  feedback?: string | null;
}) {
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
        {/* 제목 클릭 = 상세 카드(읽기 모달) 열기. 원문 이동은 제목 옆 '원문 ↗' 링크로 분리. */}
        <ReadModal
          contentId={vm.content_id}
          title={vm.title}
          url={vm.url}
          loggedIn={loggedIn}
          renderTrigger={(open) => (
            <h3 className="rec-title">
              <button type="button" className="rec-title-text" onClick={open}>
                {vm.title}
              </button>
              {vm.url && (
                <a className="ext" href={vm.url} target="_blank" rel="noopener noreferrer">
                  원문 ↗
                </a>
              )}
            </h3>
          )}
        />
        {vm.summary ? (
          <p className="rec-summary">{vm.summary}</p>
        ) : (
          vm.summary_pending && <p className="rec-pending">AI 요약 준비 중 — 잠시 후 새로고침하면 표시됩니다.</p>
        )}
        {vm.reason && <blockquote className="rec-reason">{vm.reason}</blockquote>}
        {loggedIn && <FeedbackButtons contentId={vm.content_id} current={feedback} />}
      </div>
    </article>
  );
}

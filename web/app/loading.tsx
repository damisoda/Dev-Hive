// 루트 로딩 (HIVE-94) — 서버 컴포넌트 fetch 동안 보이는 중립 인디케이터.
// 폼·피드·그래프 어디서나 어색하지 않도록 콘텐츠 모양을 가정하지 않는다.
// (graph·profile은 자체 loading.tsx로 라우트에 맞춘 스켈레톤을 보여준다.)

export default function Loading() {
  return (
    <main className="load-center" aria-busy="true" aria-live="polite">
      <span className="spinner" aria-hidden />
      <span>불러오는 중…</span>
    </main>
  );
}

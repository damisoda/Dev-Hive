// 지식그래프 로딩 (HIVE-94) — 그래프 데이터 fetch 동안 캔버스 자리를 스켈레톤으로 잡아둔다.

export default function GraphLoading() {
  return (
    <main className="graph-page" aria-busy="true">
      <div className="graph-head">
        <div>
          <h2>지식그래프</h2>
          <p className="skeleton sk-line" style={{ width: 200 }} />
        </div>
      </div>
      <div className="skeleton sk-canvas" />
    </main>
  );
}

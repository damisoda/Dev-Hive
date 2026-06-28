// 프로필 로딩 (HIVE-94) — 프로필·통계 fetch 동안 카드 그리드/잔디 자리를 스켈레톤으로.

export default function ProfileLoading() {
  return (
    <main className="feed" aria-busy="true">
      <header className="sec-head">
        <h2>프로필</h2>
        <p className="skeleton sk-line" style={{ width: 240 }} />
      </header>
      <div className="sk-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton sk-stat" />
        ))}
      </div>
      <div className="skeleton sk-canvas" style={{ height: 160, marginTop: 22 }} />
    </main>
  );
}

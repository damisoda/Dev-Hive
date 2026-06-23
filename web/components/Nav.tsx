// 상단 네비게이션 — HIVE-51의 웹사이트형 상단바를 Next.js로 이식.
// 1차 프런트는 홈(피드)만 동작, 나머지는 스캐폴드 자리.

const LINKS = [
  { href: "/", label: "홈", active: true },
  { href: "/discover", label: "디스커버", active: false },
  { href: "/curriculum", label: "커리큘럼", active: false },
  { href: "/profile", label: "프로필", active: false },
];

export function Nav() {
  return (
    <nav className="nav">
      <div className="nav-inner">
        <a className="brand" href="/">
          <span className="dot">🐝</span> Dev-Hive
        </a>
        <div className="nav-links">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} className={`nav-link${l.active ? " active" : ""}`}>
              {l.label}
            </a>
          ))}
        </div>
      </div>
    </nav>
  );
}

// 좌측 아이콘 레일 — 라벨 없이 아이콘만(RocketPunch 홈 레퍼런스). Dev-Hive 서비스용 SVG 세트.

const S = (p: { children: React.ReactNode }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    {p.children}
  </svg>
);

// 브랜드 = 벌집 헥사곤 마크
const Hive = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
    <path d="M7 3.5h10l5 8.5-5 8.5H7l-5-8.5z" />
    <path d="M12 8.2 15.2 10v3.8L12 15.6 8.8 13.8V10z" fill="currentColor" stroke="none" />
  </svg>
);

const Search = () => <S><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></S>;
const Home = () => <S><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></S>;
const Compass = () => <S><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></S>;
const Curriculum = () => <S><path d="m12 4 9 4-9 4-9-4z" /><path d="M5 10v5c0 1.5 3.1 3 7 3s7-1.5 7-3v-5" /></S>;
const Graph = () => <S><circle cx="6" cy="7" r="2.1" /><circle cx="18" cy="6" r="2.1" /><circle cx="15" cy="18" r="2.1" /><path d="m8 7.6 8-1M7.4 8.8 13.6 16" /></S>;
const Profile = () => <S><circle cx="12" cy="8" r="3.4" /><path d="M5.5 20a6.5 6.5 0 0 1 13 0" /></S>;
const Upload = () => <S><path d="M12 15V4" /><path d="m7.5 8.5 4.5-4.5 4.5 4.5" /><path d="M5 20h14" /></S>;
const More = () => <S><circle cx="5" cy="12" r="1.3" fill="currentColor" /><circle cx="12" cy="12" r="1.3" fill="currentColor" /><circle cx="19" cy="12" r="1.3" fill="currentColor" /></S>;

const NAV = [
  { href: "/discover", label: "검색", active: false, Icon: Search },
  { href: "/", label: "홈", active: true, Icon: Home },
  { href: "/discover", label: "디스커버", active: false, Icon: Compass },
  { href: "/curriculum", label: "커리큘럼", active: false, Icon: Curriculum },
  { href: "/graph", label: "지식그래프", active: false, Icon: Graph },
  { href: "/profile", label: "프로필", active: false, Icon: Profile },
  { href: "/upload", label: "업로드", active: false, Icon: Upload },
];

export function LeftRail() {
  return (
    <nav className="rail" aria-label="주요 메뉴">
      <a className="rail-brand" href="/" aria-label="Dev-Hive 홈">
        <Hive />
      </a>
      {NAV.map(({ href, label, active, Icon }, i) => (
        <a
          key={i}
          href={href}
          className={`rail-item${active ? " active" : ""}`}
          aria-label={label}
          title={label}
          aria-current={active ? "page" : undefined}
        >
          <Icon />
        </a>
      ))}
      <div className="rail-spacer" />
      <div className="rail-div" />
      <a className="rail-item" href="/profile" aria-label="더보기" title="더보기">
        <More />
      </a>
    </nav>
  );
}

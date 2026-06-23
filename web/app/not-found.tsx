import { StateView } from "@/components/StateView";

// 브랜드형 404 — 기본 Next.js 404 대신 네비/톤 유지하며 홈으로 유도.
export default function NotFound() {
  return (
    <main className="container">
      <StateView emoji="🐝" title="페이지를 찾을 수 없어요">
        주소를 확인하거나{" "}
        <a href="/" style={{ color: "var(--accent)", fontWeight: 600 }}>
          홈 피드
        </a>
        로 돌아가세요.
      </StateView>
    </main>
  );
}

import { StateView } from "./StateView";

// 아직 안 만든 라우트용 '준비 중' 자리. 1차 프런트는 홈 피드만 동작.
export function ComingSoon({ title, desc }: { title: string; desc: string }) {
  return (
    <main className="feed coming">
      <StateView emoji="🚧" title={`${title} — 준비 중`}>{desc}</StateView>
    </main>
  );
}

// 글 올리기 — 올린 글이 태깅·임베딩·Auto-HKG 편입까지. 비로그인은 시작하기 게이트.

import { getSession } from "@/lib/session";
import { UploadForm } from "@/components/UploadForm";
import { StateView } from "@/components/StateView";

export const metadata = { title: "글 올리기 · Dev-Hive" };
export const dynamic = "force-dynamic";

export default async function UploadPage() {
  const session = await getSession();
  if (!session) {
    return (
      <main className="feed coming">
        <StateView emoji="🐝" title="글을 올리려면 시작하세요">
          <a href="/onboarding" style={{ color: "var(--accent-ink)", fontWeight: 600 }}>
            시작하기 →
          </a>{" "}
          닉네임만 정하면 바로 올릴 수 있어요.
        </StateView>
      </main>
    );
  }

  return (
    <main className="feed">
      <header className="sec-head">
        <h2>글 올리기</h2>
        <p>
          올린 글이 태깅·임베딩을 거쳐 지식그래프에 자동 편입됩니다. 새로운 주제면 Auto-HKG가 노드를
          새로 만들어요.
        </p>
      </header>
      <UploadForm />
    </main>
  );
}

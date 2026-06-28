"use client";

import { useState } from "react";
import { contentTypeLabel } from "@/lib/viewmodel";

type UploadResult = {
  content_id: number;
  action: string;
  node_id?: number | null;
  node_name?: string | null;
  is_new_node: boolean;
  difficulty?: string | null;
  content_type?: string | null;
};

function graphHref(result: UploadResult) {
  const params = new URLSearchParams({
    focus: result.is_new_node && result.node_id ? `topic:${result.node_id}` : `content:${result.content_id}`,
    content: `content:${result.content_id}`,
    new: result.is_new_node ? "1" : "0",
  });
  if (result.node_id) params.set("topic", `topic:${result.node_id}`);
  return `/graph?${params.toString()}`;
}

// 글 올리기 — 제목/본문/URL → BFF /api/upload → Auto-HKG 편입 결과.
export function UploadForm() {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !body.trim()) {
      setErr("제목과 본문을 입력하세요.");
      return;
    }
    setLoading(true);
    setErr(null);
    setResult(null);
    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, body, url }),
      });
      const data = await res.json();
      if (!res.ok) setErr(data.error ?? "업로드에 실패했어요.");
      else setResult(data as UploadResult);
    } catch {
      setErr("업로드에 실패했어요.");
    } finally {
      setLoading(false);
    }
  }

  if (result) {
    return (
      <div className="up-result">
        <div className="up-result-kicker">
          <span className="up-result-dot" aria-hidden="true" />
          지식그래프 편입 완료
        </div>
        <p className="up-result-main">
          {result.is_new_node ? (
            <>
              새 주제를 만들었어요 → <strong>{result.node_name ?? "새 노드"}</strong>
            </>
          ) : (
            <>
              기존 주제 <strong>{result.node_name ?? "—"}</strong>에 편입됐어요.
            </>
          )}
        </p>
        <p className="up-result-note">
          지식그래프에서 방금 추가한 노드를 확인할 수 있어요!
        </p>
        <p className="up-result-meta">
          난이도 {result.difficulty ?? "—"} · 유형{" "}
          {result.content_type ? contentTypeLabel(result.content_type) : "—"} · #{result.content_id}
        </p>
        <div className="up-result-actions">
          <a className="read-btn" href={graphHref(result)}>
            지식그래프에서 보기 →
          </a>
          <button
            className="up-again"
            type="button"
            onClick={() => {
              setResult(null);
              setTitle("");
              setBody("");
              setUrl("");
            }}
          >
            또 올리기
          </button>
        </div>
      </div>
    );
  }

  return (
    <form className="up-form" onSubmit={onSubmit}>
      <label className="up-label">
        제목
        <input
          className="up-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="무엇에 대한 글인가요?"
          maxLength={300}
        />
      </label>
      <label className="up-label">
        본문
        <textarea
          className="up-textarea"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="경험·실전 글일수록 커뮤니티에 가치가 큽니다. 유형은 올릴 때 AI가 자동 분류해요."
          rows={12}
        />
      </label>
      <label className="up-label">
        원문 URL <span className="up-opt">(선택)</span>
        <input
          className="up-input"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://"
        />
      </label>
      {err && <p className="up-err">{err}</p>}
      <button className="up-submit" type="submit" disabled={loading}>
        {loading ? "태깅 · 임베딩 · 그래프 편입 중…" : "올리기"}
      </button>
    </form>
  );
}

"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { SOURCE_LABELS } from "@/lib/viewmodel";

// 홈 피드 필터 — 출처·난이도. 변경 시 URL 쿼리 갱신(+페이지 1로 리셋).
const SOURCES = ["velog", "huggingface", "reddit", "hn", "tistory", "github_trending", "x", "user"];
const DIFFS = ["입문", "초급", "중급", "고급"];

export function FilterBar() {
  const router = useRouter();
  const sp = useSearchParams();
  const source = sp.get("source") ?? "";
  const difficulty = sp.get("difficulty") ?? "";

  function update(key: string, val: string) {
    const p = new URLSearchParams(sp.toString());
    if (val) p.set(key, val);
    else p.delete(key);
    p.delete("page");
    const qs = p.toString();
    router.push(qs ? `/?${qs}` : "/");
  }

  return (
    <div className="filter-bar">
      <select className="filter-sel" value={source} onChange={(e) => update("source", e.target.value)} aria-label="출처 필터">
        <option value="">전체 출처</option>
        {SOURCES.map((s) => (
          <option key={s} value={s}>
            {SOURCE_LABELS[s] ?? s}
          </option>
        ))}
      </select>
      <select
        className="filter-sel"
        value={difficulty}
        onChange={(e) => update("difficulty", e.target.value)}
        aria-label="난이도 필터"
      >
        <option value="">전체 난이도</option>
        {DIFFS.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </select>
    </div>
  );
}

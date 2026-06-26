"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

// 홈 피드 검색(HIVE-94) — 제목·요약 매칭. URL ?q= 로 상태 보관(출처·난이도 필터와 결합).
// 제출 시 기존 쿼리(source/difficulty)는 보존하고 page는 1로 리셋. 레일 돋보기(?focus=search)
// 로 진입하면 자동 포커스.
export function SearchBar() {
  const router = useRouter();
  const sp = useSearchParams();
  const active = sp.get("q") ?? "";
  const [value, setValue] = useState(active);
  const inputRef = useRef<HTMLInputElement>(null);

  // 뒤로가기 등으로 URL q가 바뀌면 입력값 동기화.
  useEffect(() => setValue(active), [active]);

  // 돋보기 진입 시 1회 자동 포커스.
  useEffect(() => {
    if (sp.get("focus") === "search") inputRef.current?.focus();
    // 마운트 시 1회만.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function push(term: string) {
    const p = new URLSearchParams(sp.toString());
    if (term) p.set("q", term);
    else p.delete("q");
    p.delete("page");
    p.delete("focus");
    const qs = p.toString();
    router.push(qs ? `/?${qs}` : "/");
  }

  return (
    <form
      className="search-bar"
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        push(value.trim());
      }}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.2-3.2" />
      </svg>
      <input
        ref={inputRef}
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="제목·요약으로 검색"
        aria-label="콘텐츠 검색"
      />
      {/* 엔터와 동일 동작 — 검색을 모르는 사용자를 위한 명시적 버튼 */}
      <button type="submit" className="search-go" aria-label="검색">
        검색
      </button>
    </form>
  );
}

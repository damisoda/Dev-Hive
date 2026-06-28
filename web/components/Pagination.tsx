"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

// 피드 페이지네이션 — 기존 쿼리(출처·난이도) 보존하며 page만 변경.
export function Pagination({ page, totalPages }: { page: number; totalPages: number }) {
  const sp = useSearchParams();
  function href(p: number) {
    const q = new URLSearchParams(sp.toString());
    q.set("page", String(p));
    return `/?${q.toString()}`;
  }
  return (
    <nav className="pager" aria-label="페이지 이동">
      {page > 1 ? (
        <Link className="pager-btn" href={href(page - 1)}>
          ← 이전
        </Link>
      ) : (
        <span className="pager-btn disabled">← 이전</span>
      )}
      <span className="pager-info">
        {page} / {totalPages}
      </span>
      {page < totalPages ? (
        <Link className="pager-btn" href={href(page + 1)}>
          다음 →
        </Link>
      ) : (
        <span className="pager-btn disabled">다음 →</span>
      )}
    </nav>
  );
}

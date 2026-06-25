"use client";

// 학습경로 단계용 '읽음 처리 링크'(HIVE-97). 제목 클릭 시 원문을 새 탭으로 열면서
// 동시에 읽음 처리(POST /api/read, fire-and-forget)한다 — 추천받은 글을 경로에서 바로
// '완료'로 만들 수 있게. 무거운 ReadModal 대신 링크+로깅만(경로는 한눈 요약이라 가볍게).
// 비로그인이면 로깅 스킵(BFF가 쿠키로 본인 식별). url 없으면 그냥 텍스트.
export function ReadLink({
  contentId,
  url,
  loggedIn,
  className,
  children,
}: {
  contentId: number;
  url: string | null;
  loggedIn: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  function markRead() {
    if (!loggedIn) return;
    // 읽음 처리는 성공/실패와 무관하게 원문 이동을 막지 않는다.
    fetch("/api/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content_id: contentId }),
      keepalive: true, // 새 탭으로 떠나도 요청 유지
    }).catch(() => {});
  }

  if (!url) return <span className={className}>{children}</span>;
  return (
    <a className={className} href={url} target="_blank" rel="noopener noreferrer" onClick={markRead}>
      {children}
    </a>
  );
}

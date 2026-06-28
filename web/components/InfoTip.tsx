// (i) 아이콘 + CSS-only hover 툴팁. 클라이언트 JS 없이 서버 컴포넌트에서 그대로 쓰인다.
// 스타일은 globals.css의 .info-tip. tabindex로 키보드 포커스 시에도 노출.

export function InfoTip({ text }: { text: string }) {
  return (
    <span className="info-tip" data-tip={text} tabIndex={0} aria-label={text} role="img">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5" />
        <circle cx="12" cy="7.6" r="0.5" fill="currentColor" stroke="none" />
      </svg>
    </span>
  );
}

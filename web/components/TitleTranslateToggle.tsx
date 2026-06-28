"use client";

import { useState } from "react";

// 영문 제목 + 한글 번역 토글 (HIVE-66). 제목 클릭 시 상세 카드(읽기 모달)를 연다(onTitleClick).
// 같은 줄에 흐린 '번역 보기' 텍스트 버튼을 붙이고, 누르면 한글 번역이 제목 아래 한 줄로 펼쳐진다.
// 노출 판단(title_ko 유무·원문과 다름)은 호출부(ContentCard)에서 한다.
export function TitleTranslateToggle({
  title,
  titleKo,
  onTitleClick,
}: {
  title: string;
  titleKo: string;
  onTitleClick: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="post-title-block">
      <button type="button" className="post-title-tr post-title-btn" onClick={onTitleClick}>
        {title}
      </button>
      <button type="button" className="title-tr-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "접기" : "번역 보기"}
      </button>
      {open && <span className="post-title-ko">{titleKo}</span>}
    </div>
  );
}

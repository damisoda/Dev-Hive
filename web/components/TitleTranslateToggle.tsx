"use client";

import { useState } from "react";

// 영문 제목 + 한글 번역 토글 (HIVE-66). 제목은 그대로 두고, 같은 줄에 흐린 '번역 보기'
// 텍스트 링크를 붙인다. 누르면 한글 번역이 제목 아래 한 줄로 펼쳐지고 '접기'로 바뀐다.
// 노출 판단(title_ko 유무·원문과 다름)은 호출부(ContentCard)에서 한다.
export function TitleTranslateToggle({
  title,
  titleKo,
  url,
}: {
  title: string;
  titleKo: string;
  url?: string | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="post-title-block">
      {url ? (
        <a className="post-title-tr" href={url} target="_blank" rel="noopener noreferrer">
          {title}
        </a>
      ) : (
        <span className="post-title-tr">{title}</span>
      )}
      <button type="button" className="title-tr-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "접기" : "번역 보기"}
      </button>
      {open && <span className="post-title-ko">{titleKo}</span>}
    </div>
  );
}

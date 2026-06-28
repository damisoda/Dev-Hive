"use client";

import { ReadModal } from "./ReadModal";
import { TitleTranslateToggle } from "./TitleTranslateToggle";
import { externalUrl } from "@/lib/viewmodel";

// 카드 제목을 '읽기 모달' 트리거로 묶는 클라이언트 섬.
// 서버 컴포넌트(ContentCard/RecommendationCard)는 함수 prop(renderTrigger)을 클라이언트로
// 넘길 수 없으므로, 트리거 함수 생성을 이 클라이언트 경계 안쪽으로 가둔다.
// variant: "feed"(홈/디스커버 카드) | "rec"(커리큘럼 추천 카드).
export function ReadableTitle({
  contentId,
  title,
  url,
  loggedIn,
  titleKo,
  variant,
}: {
  contentId: number;
  title: string;
  url?: string | null;
  loggedIn: boolean;
  titleKo?: string | null;
  variant: "feed" | "rec";
}) {
  const ko = titleKo?.trim();
  const showTitleToggle = Boolean(ko && ko !== title.trim());
  const ext = externalUrl(url); // 외부 원문만 링크(user:// 합성 url 제외)

  return (
    <ReadModal
      contentId={contentId}
      title={title}
      url={url}
      loggedIn={loggedIn}
      titleKo={titleKo}
      renderTrigger={(open) =>
        variant === "rec" ? (
          <h3 className="rec-title">
            <button type="button" className="rec-title-text" onClick={open}>
              {title}
            </button>
            {ext && (
              <a className="ext" href={ext} target="_blank" rel="noopener noreferrer">
                원문 ↗
              </a>
            )}
          </h3>
        ) : showTitleToggle ? (
          <TitleTranslateToggle title={title} titleKo={ko!} onTitleClick={open} />
        ) : (
          <button type="button" className="post-title post-title-btn" onClick={open}>
            {title}
          </button>
        )
      }
    />
  );
}

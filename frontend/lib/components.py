"""HIVE-34: 페이지 공통 UI 컴포넌트.

피드/커리큘럼/프로필에서 재사용하는 카드. 인라인 마크업 중복 제거.
(비주얼 디자인 시스템은 Layer 3 — 여기선 구조/기능만)
"""
from datetime import date, timedelta

import streamlit as st

from lib.api import clear_feedback, mark_read, set_feedback


def render_contribution_heatmap(heatmap: dict, *, weeks: int = 26) -> None:
    """GitHub식 잔디 히트맵 (HIVE-37). heatmap = {YYYY-MM-DD: 읽은 수}.

    최근 `weeks`주를 주(열) × 요일(행) 격자로 렌더. 색은 읽은 수 단계별.
    """
    today = date.today()
    # 이번 주 일요일 끝 기준으로 격자 정렬 (월~일 행)
    start = today - timedelta(days=weeks * 7 - 1)
    start -= timedelta(days=start.weekday())  # 그 주 월요일로 정렬

    def _color(c: int) -> str:
        if c <= 0:
            return "#ebedf0"
        if c <= 2:
            return "#9be9a8"
        if c <= 4:
            return "#40c463"
        if c <= 6:
            return "#30a14e"
        return "#216e39"

    # 열(주) 단위로 7일 셀 생성
    cols_html = []
    d = start
    while d <= today:
        cells = []
        for _ in range(7):
            cnt = heatmap.get(d.isoformat(), 0) if d <= today else -1
            if cnt < 0:
                cells.append("<div style='width:11px;height:11px'></div>")
            else:
                cells.append(
                    f"<div title='{d.isoformat()}: {cnt}' "
                    f"style='width:11px;height:11px;border-radius:2px;"
                    f"background:{_color(cnt)}'></div>"
                )
            d += timedelta(days=1)
        cols_html.append(
            "<div style='display:flex;flex-direction:column;gap:3px'>"
            + "".join(cells)
            + "</div>"
        )
    grid = (
        "<div style='display:flex;gap:3px;overflow-x:auto;padding:4px 0'>"
        + "".join(cols_html)
        + "</div>"
    )
    st.markdown(grid, unsafe_allow_html=True)

# 피드백 버튼 (라벨, 내부 키). HIVE-37
_FEEDBACK_BUTTONS = [
    ("이해했어요", "understood"),
    ("어려워요", "too_hard"),
    ("더 보고 싶어요", "want_more"),
    ("관심없어요", "not_interested"),
]


def _feedback_row(content_id: int, user_id: int, current: str | None, key_prefix: str) -> None:
    """콘텐츠 피드백 버튼 4종. 이미 누른 버튼을 다시 누르면 해제(토글)."""
    cols = st.columns(len(_FEEDBACK_BUTTONS))
    for col, (label, fb) in zip(cols, _FEEDBACK_BUTTONS):
        active = current == fb
        with col:
            if st.button(
                ("✓ " if active else "") + label,
                key=f"{key_prefix}_fb_{fb}_{content_id}",
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                if active:
                    clear_feedback(user_id, content_id)   # 같은 버튼 재클릭 → 해제
                else:
                    set_feedback(user_id, content_id, fb)
                st.rerun()


def content_card(
    item: dict,
    user_id: int,
    *,
    key_prefix: str = "content",
    feedback_map: dict | None = None,
) -> None:
    """/content 아이템 카드 — 제목·메타·태그·읽음 버튼·피드백 버튼.

    feedback_map: {content_id: feedback} (페이지에서 1회 조회해 전달). None이면 미표시.
    """
    with st.container(border=True):
        st.markdown(f"### [{item['title']}]({item.get('url') or '#'})")
        badges = []
        if item.get("source"):
            badges.append(f"`{item['source']}`")
        if item.get("author_name"):
            badges.append(item["author_name"])
        if item.get("difficulty"):
            badges.append(f"`{item['difficulty']}`")
        if item.get("content_type"):
            badges.append(f"`{item['content_type']}`")
        if item.get("quality_score") is not None:
            badges.append(f"품질 {item['quality_score']:.2f}")
        if badges:
            st.markdown(" · ".join(badges))
        if item.get("tags"):
            st.markdown(" ".join(f":blue-background[{t}]" for t in item["tags"]))
        cols = st.columns([1, 3])
        with cols[0]:
            if st.button("읽음 처리", key=f"{key_prefix}_read_{item['id']}"):
                if mark_read(user_id, item["id"]):
                    st.toast("읽음 처리됨")
                    st.rerun()
        with cols[1]:
            if item.get("engagement_likes") is not None:
                st.caption(
                    f"추천 {item['engagement_likes']} · 댓글 {item.get('engagement_comments', 0)}"
                )
        if feedback_map is not None:
            _feedback_row(item["id"], user_id, feedback_map.get(item["id"]), key_prefix)


def recommendation_card(rec: dict, user_id: int, idx: int) -> None:
    """/recommend 아이템 카드 — 순위 + GraphRAG 근거(reason) 강조 + 읽음 버튼."""
    with st.container(border=True):
        cols = st.columns([1, 9])
        with cols[0]:
            st.markdown(f"# {idx}")
        with cols[1]:
            st.markdown(f"### {rec['title']}")
            if rec.get("reason"):
                st.markdown(f"> {rec['reason']}")          # GraphRAG 근거 = 차별점, 강조
            else:
                st.caption("추천 근거(GraphRAG)는 API 키 설정 시 자연어로 생성됩니다.")
            if rec.get("score") is not None:
                st.caption(f"적합도 {rec['score']:.2f}")
            if st.button("읽음 처리", key=f"rec_read_{rec['content_id']}"):
                if mark_read(user_id, rec["content_id"]):
                    st.toast("읽음 처리됨. 다음 추천을 갱신합니다.")
                    st.rerun()

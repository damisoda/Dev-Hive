"""HIVE-34: 페이지 공통 UI 컴포넌트.

피드/커리큘럼/프로필에서 재사용하는 카드. 인라인 마크업 중복 제거.
표시 구조(배지·버튼 정의·필드 정리)는 lib/viewmodel이 만들고, 여기선 st.* 렌더만.
(비주얼 디자인 시스템은 Layer 3 — 여기선 구조/기능만)
"""
import html
from datetime import date, timedelta

import streamlit as st

from lib.api import clear_feedback, mark_read, set_feedback
from lib.ui import call
from lib.viewmodel import (
    FEEDBACK_BUTTONS,
    content_meta,
    content_pills,
    recommendation_view,
)


def pills_html(pills: list[dict]) -> str:
    """viewmodel pill 목록 [{'text','fg','bg'}] → 알약 뱃지 행 HTML."""
    spans = "".join(
        f"<span class='dh-pill' style='color:{p['fg']};background:{p['bg']}'>"
        f"{html.escape(p['text'])}</span>"
        for p in pills
    )
    return f"<div class='dh-pills'>{spans}</div>"


def chips_html(tags: list[str]) -> str:
    """태그 목록 → chip 행 HTML."""
    spans = "".join(f"<span class='dh-chip'>{html.escape(str(t))}</span>" for t in tags)
    return f"<div class='dh-chips'>{spans}</div>"


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

def _feedback_row(content_id: int, user_id: int, current: str | None, key_prefix: str) -> None:
    """콘텐츠 피드백 버튼 4종(정의는 viewmodel.FEEDBACK_BUTTONS). 재클릭 시 해제(토글)."""
    cols = st.columns(len(FEEDBACK_BUTTONS))
    for col, (label, fb) in zip(cols, FEEDBACK_BUTTONS):
        active = current == fb
        with col:
            if st.button(
                ("✓ " if active else "") + label,
                key=f"{key_prefix}_fb_{fb}_{content_id}",
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                if active:
                    # 같은 버튼 재클릭 → 해제. 실패 시 call이 안내 렌더 → rerun 생략(상태 유지)
                    if call(clear_feedback, user_id, content_id,
                            retry_key=f"fb_clear_{content_id}") is None:
                        return
                else:
                    if call(set_feedback, user_id, content_id, fb,
                            retry_key=f"fb_set_{content_id}") is None:
                        return
                st.rerun()


def _handle_read_result(resp: dict | None) -> bool:
    """mark_read 응답 처리 — 레벨업이면 축하 알림(HIVE-36/49). 성공 시 True.

    토스트는 rerun을 넘어 유지되므로, 읽음 직후 rerun해도 메시지가 보인다.
    """
    if not resp:
        return False
    if resp.get("leveled_up"):
        st.toast(f"레벨 업 — '{resp.get('new_level')}' 단계에 도달했어요")
    else:
        st.toast("읽음 처리됨")
    return True


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
        pills = content_pills(item)            # source / 난이도 / 타입 알약 뱃지 (viewmodel)
        if pills:
            st.markdown(pills_html(pills), unsafe_allow_html=True)
        if item.get("tags"):
            st.markdown(chips_html(item["tags"]), unsafe_allow_html=True)
        cols = st.columns([1, 3])
        with cols[0]:
            if st.button("읽음 처리", key=f"{key_prefix}_read_{item['id']}"):
                resp = call(mark_read, user_id, item["id"], retry_key=f"read_{item['id']}")
                if _handle_read_result(resp):
                    st.rerun()
        with cols[1]:
            meta = content_meta(item)          # 작성자 · 추천/댓글 · 품질 (viewmodel)
            if meta:
                st.caption(meta)
        if feedback_map is not None:
            _feedback_row(item["id"], user_id, feedback_map.get(item["id"]), key_prefix)


def recommendation_card(
    rec: dict, user_id: int, idx: int, *, feedback_map: dict | None = None
) -> None:
    """/recommend 카드 — 순위 + 제목(원문 링크) + 가공 요약 + GraphRAG 근거 + 메타 + 피드백 + 읽음.

    feedback_map: {content_id: feedback}. None이면 피드백 버튼 미표시.
    """
    vm = recommendation_view(rec)
    with st.container(border=True):
        cols = st.columns([1, 11])
        with cols[0]:
            # 순위 = 원형 뱃지
            st.markdown(f"<div class='dh-rank'>{idx}</div>", unsafe_allow_html=True)
        with cols[1]:
            # 제목 = 원문 링크(HIVE-49). url 없으면 비활성('#').
            st.markdown(f"### [{vm['title']}]({vm['url'] or '#'})")
            if vm["summary_pending"]:
                # 요약은 백그라운드 lazy 가공(HIVE-49) — 첫 로드엔 비어 있을 수 있다.
                st.caption("*AI 요약 준비 중 — 잠시 후 새로고침하면 표시됩니다.*")
            else:
                st.markdown(vm["summary"])              # 추천 확정 시 lazy 가공된 요약(one_liner)
            badge_bits = []
            if vm["pills"]:
                badge_bits.append(pills_html(vm["pills"]))
            if vm["match"] is not None:                 # 적합도 → '매치 87%'
                badge_bits.append(f"<span class='dh-match'>매치 {vm['match']}%</span>")
            if badge_bits:
                st.markdown(
                    "<div style='display:flex;align-items:center;gap:10px'>"
                    + "".join(badge_bits) + "</div>",
                    unsafe_allow_html=True,
                )
            if vm["reason"]:
                st.markdown(f"> {vm['reason']}")           # GraphRAG 근거 = 차별점, 강조
            else:
                st.caption("추천 근거(GraphRAG)는 API 키 설정 시 자연어로 생성됩니다.")
            if st.button("읽음 처리", key=f"rec_read_{vm['content_id']}"):
                resp = call(mark_read, user_id, vm["content_id"],
                            retry_key=f"rec_read_{vm['content_id']}")
                if _handle_read_result(resp):
                    st.rerun()
            if feedback_map is not None:
                _feedback_row(vm["content_id"], user_id, feedback_map.get(vm["content_id"]), "rec")

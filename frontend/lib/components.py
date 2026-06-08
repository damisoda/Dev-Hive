"""HIVE-34: 페이지 공통 UI 컴포넌트.

피드/커리큘럼/프로필에서 재사용하는 카드. 인라인 마크업 중복 제거.
(비주얼 디자인 시스템은 Layer 3 — 여기선 구조/기능만)
"""
import streamlit as st

from lib.api import mark_read


def content_card(item: dict, user_id: int, *, key_prefix: str = "content") -> None:
    """/content 아이템 카드 — 제목·메타·태그·읽음 버튼."""
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

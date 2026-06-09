"""사용자 업로드 — 올린 글이 그래프에 편입되는 데모 클라이맥스.

제목/본문(+선택 URL)을 올리면 태깅 → 임베딩 → 적재 → Auto-HKG 편입까지 돌고,
기존 노드 편입 또는 새 하위/최상위 노드 생성 결과를 보여준다.
"""
import streamlit as st

from lib.api import upload_content

st.set_page_config(page_title="업로드 · Dev-Hive", layout="centered")
st.title("글 올리기")
st.caption("올린 글이 태깅·임베딩을 거쳐 지식그래프에 자동 편입됩니다. 새로운 주제면 Auto-HKG가 노드를 새로 만듭니다.")

if "user_id" not in st.session_state:
    st.warning("먼저 메인 페이지에서 온보딩을 완료해주세요.")
    st.stop()

with st.form("upload_form"):
    title = st.text_input("제목")
    body = st.text_area("본문", height=260, placeholder="경험/실전 글일수록 좋아요.")
    url = st.text_input("원문 URL (선택)")
    submitted = st.form_submit_button("올리기", type="primary")

if submitted:
    if not title.strip() or not body.strip():
        st.warning("제목과 본문을 입력해주세요.")
        st.stop()
    with st.spinner("태깅 · 임베딩 · 그래프 편입 중…"):
        res = upload_content(
            title.strip(), body.strip(), url.strip() or None, st.session_state["user_id"]
        )
    if not res:
        st.stop()

    st.success("지식그래프에 편입되었습니다.")
    if res.get("is_new_node"):
        st.balloons()
        st.markdown(
            f"**Auto-HKG가 새 주제를 생성했습니다 → `{res.get('node_name')}`** "
            "— 그래프에서 금색 노드로 보입니다."
        )
    else:
        st.markdown(f"기존 주제 **{res.get('node_name') or '—'}** 에 편입되었습니다.")
    st.caption(
        f"난이도: {res.get('difficulty')} · 유형: {res.get('content_type')} · "
        f"content_id={res.get('content_id')}"
    )
    # 그래프 페이지로 핸드오프: 도착 시 캐시를 비우고 배너를 띄워 새 노드를 바로 보여준다.
    st.session_state["just_uploaded"] = {
        "node_name": res.get("node_name"),
        "is_new_node": res.get("is_new_node"),
    }
    st.page_link("pages/4_그래프.py", label="지식그래프에서 보기 →")

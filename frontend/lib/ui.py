"""공통 UI 테마/CSS 주입 + 스트림릿 어댑터 (HIVE-49 UI 폴리시 / HIVE-51 이식성).

Streamlit 기본 티(헤더·메뉴·Deploy·Running 인디케이터)를 줄이고, Pretendard 폰트 +
라운드 카드 + 일관된 액센트로 '디자인된' 느낌을 준다. 각 페이지가 set_page_config 직후 style()을 호출한다.

call(): 순수 클라이언트(lib/api)의 ApiError를 잡아 친화적으로 렌더하는 가드 헬퍼.
스트림릿 결합은 이 파일과 components.py·pages에만 — api/viewmodel은 스트림릿 무지.
"""
import streamlit as st

from lib.api import ApiError


def call(fn, *args, retry_key: str | None = None, **kwargs):
    """API 호출 가드 — ApiError를 st.error로 친화적으로 렌더하고 None 반환.

    연결 실패(백엔드 꺼짐)면 실행 안내 + '다시 시도' 버튼(st.rerun)을 함께 보여준다.
    retry_key: 같은 페이지에서 같은 함수를 여러 번 가드할 때 버튼 키 충돌 방지용.
    """
    try:
        return fn(*args, **kwargs)
    except ApiError as e:
        if e.is_connection:
            st.error(
                "백엔드 서버가 꺼져 있습니다. 터미널에서 `uvicorn app.main:app`을 "
                "실행한 뒤 새로고침하세요."
            )
        else:
            st.error(str(e))
        if st.button("다시 시도", key=f"retry_{retry_key or fn.__name__}"):
            st.rerun()
        return None

_ACCENT = "#5b5bd6"

_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

:root { --dh-accent:#5b5bd6; --dh-accent-soft:#ececfb; --dh-border:#ececf3; }

/* Pretendard 전역 적용 */
html, body, [class*="css"], .stApp, button, input, textarea, select {
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif !important;
}

/* Streamlit 기본 크롬 숨김 — 'Streamlit 티' 제거 */
header[data-testid="stHeader"] { background: transparent; height: 0; }
#MainMenu, [data-testid="stToolbar"], [data-testid="stDeployButton"],
[data-testid="stStatusWidget"], footer { display: none !important; }

/* 본문 폭/여백 — 좌우 넉넉히, 사이드바와 붙지 않게 */
.block-container { padding: 2.4rem 3.5rem 3rem 3.5rem; max-width: 1120px; }
@media (max-width: 900px) { .block-container { padding-left: 1.2rem; padding-right: 1.2rem; } }

/* 타이포 */
h1 { font-weight: 800; letter-spacing: -0.025em; }
h2, h3 { font-weight: 700; letter-spacing: -0.015em; }

/* 카드 — st.container(border=True) */
[data-testid="stVerticalBlockBorderWrapper"] {
  border: 1px solid var(--dh-border) !important;
  border-radius: 16px !important;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(20,20,50,.04);
  transition: box-shadow .16s ease, transform .16s ease, border-color .16s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
  box-shadow: 0 8px 26px rgba(91,91,214,.10);
  border-color: #d9d9ef !important;
  transform: translateY(-2px);
}

/* 버튼 */
.stButton > button {
  border-radius: 10px; font-weight: 600; border: 1px solid var(--dh-border);
  transition: all .14s ease;
}
.stButton > button:hover {
  border-color: var(--dh-accent); color: var(--dh-accent); background: var(--dh-accent-soft);
}
.stButton > button[kind="primary"] {
  background: var(--dh-accent); border-color: var(--dh-accent); color: #fff;
}

/* 진행바 */
.stProgress > div > div > div > div { background: linear-gradient(90deg, var(--dh-accent), #8e7bff); }

/* 입력/셀렉트 라운드 */
[data-baseweb="select"] > div, .stTextInput input, .stTextArea textarea, .stNumberInput input {
  border-radius: 10px !important;
}

/* 사이드바 */
[data-testid="stSidebar"] { background: #fafaff; border-right: 1px solid var(--dh-border); }

/* 링크 */
a { color: var(--dh-accent); text-decoration: none; }
a:hover { text-decoration: underline; }

/* 인라인 코드 = 뱃지 느낌 */
code { background: var(--dh-accent-soft); color: #4a4ac0; border-radius: 6px;
       padding: 1px 6px; font-size: .85em; }

/* 콜아웃(st.info/success/warning/error) — 안쪽 좌우 여백 확보(글씨가 모서리에 붙지 않게) */
[data-testid="stAlert"] {
  border-radius: 12px;
  padding: 0.85rem 1.1rem !important;
}
[data-testid="stAlert"] p { margin: 0; }
/* 인용(blockquote) — GraphRAG 근거 등 */
blockquote {
  border-left: 3px solid var(--dh-accent);
  background: var(--dh-accent-soft);
  padding: 0.5rem 0.95rem; margin: 0.4rem 0;
  border-radius: 0 8px 8px 0;
}
</style>
"""


def style() -> None:
    """전 페이지 공통 테마/CSS 주입. set_page_config 직후 호출."""
    st.markdown(_CSS, unsafe_allow_html=True)

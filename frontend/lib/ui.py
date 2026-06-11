"""공통 UI 테마/CSS 주입 + 스트림릿 어댑터 (HIVE-49 UI 폴리시 / HIVE-51 이식성).

Streamlit 기본 티(헤더·메뉴·Deploy·Running 인디케이터)를 줄이고, Pretendard 폰트 +
라운드 카드 + 일관된 액센트로 '디자인된' 느낌을 준다. 각 페이지가 set_page_config 직후 style()을 호출한다.

call(): 순수 클라이언트(lib/api)의 ApiError를 잡아 친화적으로 렌더하는 가드 헬퍼.
스트림릿 결합은 이 파일과 components.py·pages에만 — api/viewmodel은 스트림릿 무지.
"""
import html

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

:root {
  --dh-accent:#5b5bd6; --dh-accent-soft:#ececfb; --dh-border:#ececf3;
  --dh-bg:#f7f8fc; --dh-card:#ffffff; --dh-ink:#23243a; --dh-ink-soft:#5a5e72;
}

/* 라이트 커뮤니티 톤 — 본문은 옅은 블루그레이, 카드는 흰색 */
.stApp { background: var(--dh-bg); }

/* Pretendard 전역 적용 */
html, body, [class*="css"], .stApp, button, input, textarea, select {
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif !important;
}

/* Streamlit 기본 크롬 숨김 — 'Streamlit 티' 제거 */
header[data-testid="stHeader"] { background: transparent; height: 0; }
#MainMenu, [data-testid="stToolbar"], [data-testid="stDeployButton"],
[data-testid="stStatusWidget"], footer { display: none !important; }

/* 본문 폭/여백 — 전체 화면 사용(상단 네비 웹 레이아웃), 좌우는 비율 패딩만 */
.block-container { padding: 1.6rem 4vw 3rem 4vw; max-width: 100%; }
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

/* 사이드바 숨김 — 네비게이션은 상단 바(ui.header)로. 웹사이트형 레이아웃 */
[data-testid="stSidebar"], [data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapseButton"] {
  display: none !important;
}

/* 상단 네비게이션 링크(st.page_link) — 알약 메뉴. 현재 페이지는 액센트 강조 */
[data-testid="stPageLink"] a, [data-testid="stPageLink"] span[aria-disabled] {
  border-radius: 999px; padding: .28rem 1.05rem; font-weight: 600;
  color: #3d3f56; justify-content: center; width: 100%;
}
[data-testid="stPageLink"] a:hover {
  background: var(--dh-accent-soft); color: var(--dh-accent); text-decoration: none;
}
[data-testid="stPageLink"] a[aria-current="page"],
[data-testid="stPageLink"] a[aria-current="page"] p {
  background: var(--dh-accent-soft); color: var(--dh-accent) !important; font-weight: 700;
}

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

/* ── HIVE-51 리디자인: 브랜드 헤더 / pill·chip / 순위 뱃지 / 폼 카드 / 히어로 ── */

/* 브랜드 헤더 — 모든 페이지 상단 공통 (ui.header()) */
.dh-header {
  display: flex; justify-content: space-between; align-items: center;
  padding-bottom: .85rem; margin-bottom: 1.1rem;
  border-bottom: 1px solid var(--dh-border);
}
.dh-logo { font-size: 1.22rem; font-weight: 800; letter-spacing: -0.02em; color: var(--dh-ink); }
.dh-logo em { font-style: normal; color: var(--dh-accent); }
.dh-user-chip {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--dh-card); border: 1px solid var(--dh-border); border-radius: 999px;
  padding: 4px 13px; font-size: .85rem; font-weight: 600; color: #3c3e54;
  box-shadow: 0 1px 2px rgba(20,20,50,.05);
}
.dh-user-chip .lvl {
  background: var(--dh-accent-soft); color: var(--dh-accent);
  border-radius: 999px; padding: 1px 8px; font-size: .76rem; font-weight: 700;
}

/* pill(알약 뱃지) — 난이도·타입·source. 색은 viewmodel 토큰에서 인라인 주입 */
.dh-pills { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 2px 0 6px 0; }
.dh-pill {
  display: inline-flex; align-items: center; border-radius: 999px;
  padding: 2px 11px; font-size: .78rem; font-weight: 600; line-height: 1.55;
  white-space: nowrap;
}

/* 태그 chip */
.dh-chips { display: flex; flex-wrap: wrap; gap: 5px; margin: 2px 0 4px 0; }
.dh-chip {
  display: inline-flex; border-radius: 7px; padding: 1px 9px;
  font-size: .76rem; font-weight: 500;
  background: var(--dh-accent-soft); color: #4a4ac0;
}

/* 추천 순위 원형 뱃지 */
.dh-rank {
  display: inline-flex; width: 36px; height: 36px; border-radius: 50%;
  background: linear-gradient(135deg, var(--dh-accent), #8e7bff); color: #fff;
  font-weight: 800; font-size: 1.02rem;
  align-items: center; justify-content: center;
  box-shadow: 0 3px 10px rgba(91,91,214,.30);
}
/* '매치 87%' 강조 */
.dh-match { color: var(--dh-accent); font-weight: 700; font-size: .85rem; }

/* '다음 추천 학습' 강조 뱃지 (커리큘럼 미니 카드) */
.dh-next-badge {
  display: inline-flex; border-radius: 999px; padding: 2px 10px;
  font-size: .74rem; font-weight: 700;
  background: var(--dh-accent); color: #fff;
  box-shadow: 0 2px 8px rgba(91,91,214,.28);
}

/* st.form도 카드로 (업로드 폼) */
[data-testid="stForm"] {
  background: var(--dh-card); border: 1px solid var(--dh-border) !important;
  border-radius: 16px !important; padding: 1.4rem 1.5rem;
  box-shadow: 0 1px 2px rgba(20,20,50,.04);
}

/* 홈 히어로 블록 */
.dh-hero {
  background: linear-gradient(135deg, #ececfb 0%, #f9f9ff 55%, #f7f8fc 100%);
  border: 1px solid var(--dh-border); border-radius: 20px;
  padding: 2.1rem 2.3rem; margin-bottom: 1.5rem;
}
.dh-hero .quote { font-size: 1.55rem; font-weight: 800; letter-spacing: -0.03em;
  color: var(--dh-ink); margin: 0 0 .55rem 0; }
.dh-hero .quote em { font-style: normal; color: var(--dh-accent); }
.dh-hero .sub { color: var(--dh-ink-soft); font-size: .98rem; margin: 0; }

/* 그래프 범례 컬러 chip */
.dh-legend { display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0 10px 0; }
.dh-legend-chip {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--dh-card); border: 1px solid var(--dh-border); border-radius: 999px;
  padding: 3px 11px; font-size: .8rem; font-weight: 600; color: #3c3e54;
}
.dh-legend-chip .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }

/* iframe(그래프 등)도 라운드 */
iframe { border-radius: 12px; }

/* 통계 카드 안 metric 중앙 정돈 */
[data-testid="stMetric"] { padding: .1rem .2rem; }
[data-testid="stMetricLabel"] p { color: var(--dh-ink-soft); font-size: .85rem; }
</style>
"""


def style() -> None:
    """전 페이지 공통 테마/CSS 주입. set_page_config 직후 호출."""
    st.markdown(_CSS, unsafe_allow_html=True)


# 상단 네비게이션 메뉴 (사이드바 대체). 경로는 메인 스크립트(app.py) 기준.
_NAV_PAGES = [
    ("app.py", "홈"),
    ("pages/1_피드.py", "피드"),
    ("pages/2_커리큘럼.py", "커리큘럼"),
    ("pages/4_그래프.py", "지식그래프"),
    ("pages/3_프로필.py", "프로필"),
    ("pages/5_업로드.py", "업로드"),
]


def header() -> None:
    """공통 브랜드 헤더 + 상단 네비게이션 — 웹사이트형 레이아웃(사이드바 없음).

    각 페이지에서 style() 다음에 호출한다. 1행: 로고 + 유저 칩(세션에 있으면),
    2행: 가로 메뉴(st.page_link — 세션 유지 SPA 전환. HTML 앵커는 전체 리로드로
    session_state가 날아가므로 금지).
    """
    name = st.session_state.get("display_name")
    level = st.session_state.get("current_level")
    chip = ""
    if name:
        lvl = f"<span class='lvl'>{html.escape(str(level))}</span>" if level else ""
        chip = f"<span class='dh-user-chip'>🐝 {html.escape(str(name))} {lvl}</span>"
    st.markdown(
        f"<div class='dh-header'><span class='dh-logo'>🐝 Dev-<em>Hive</em></span>{chip}</div>",
        unsafe_allow_html=True,
    )
    nav_cols = st.columns([1, 1, 1.2, 1.2, 1, 1, 6])   # 마지막 칸 = 우측 여백(전체폭에서 메뉴 컴팩트 유지)
    for col, (path, label) in zip(nav_cols, _NAV_PAGES):
        with col:
            st.page_link(path, label=label, use_container_width=True)

import os

import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Dev-Hive", layout="wide")

st.title("Dev-Hive")
st.caption("커뮤니티의 경험이 곧 다른 사람의 학습이 되는 플랫폼")

st.info("Walking Skeleton. 페이지는 frontend/pages/ 아래에 추가한다.")

# 페이지 구성 (예정)
# pages/1_피드.py
# pages/2_커리큘럼.py
# pages/3_프로필.py

import streamlit as st
from supabase import create_client, Client

# 1. 基礎設定與 Supabase 初始化
st.set_page_config(page_title="財務規劃系統入口", layout="wide")

# 請確保在 Streamlit Secrets 或 .env 中設定好連線資訊
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()
st.session_state.supabase_client = supabase  # <-- 新增這行：把連線存入狀態中

# 2. 狀態檢查：初始化登入狀態
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_email" not in st.session_state:
    st.session_state.user_email = None

# 3. 定義頁面導航
def logout():
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.rerun()

# 根據登入狀態動態定義頁面
if not st.session_state.authenticated:
    # 未登入：強制指向登入頁
    pg = st.navigation([st.Page("views/login.py", title="系統登入", icon="🔒")])
else:
    # 已登入：解鎖財務子系統與登出功能
    pages = {
        "財務試算系統": [
            st.Page("views/age65.py", title="退休生活花費預估", icon="📊", default=True),
            st.Page("views/whichone70.py", title="差一歲退休差異多大", icon="📈"),
            st.Page("views/yahoostock.py", title="投資組合試算", icon="📉"),
            st.Page("views/retirement_prep.py", title="退休金準備", icon="🎯"),
            st.Page("views/labor_retirement.py", title="勞退推算版", icon="💼"),
        ],
        "帳戶管理": [
            st.Page(logout, title="登出系統", icon="🚪"),
        ]
    }
    pg = st.navigation(pages)
# 4. 執行導航
pg.run()

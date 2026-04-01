import streamlit as st

# 從 session_state 取得剛剛在 app.py 存入的 Supabase 連線
supabase = st.session_state.supabase_client

def login_page():
    st.title("財務規劃系統入口")
    st.subheader("請登入以存取專業試算工具")

    with st.form("login_form"):
        email = st.text_input("電子郵件 (Email)")
        password = st.text_input("密碼 (Password)", type="password")
        submit = st.form_submit_button("登入")

        if submit:
            try:
                # 呼叫 Supabase 進行驗證
                response = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                
                # 登入成功：更新 Session State
                st.session_state.authenticated = True
                st.session_state.user_email = email
                st.success("登入成功！正在導向首頁...")
                st.rerun()
                
            except Exception as e:
                st.error("登入失敗：請檢查帳號密碼。")

# 執行頁面
login_page()

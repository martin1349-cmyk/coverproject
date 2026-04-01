import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import os
import datetime
from google import genai

# =====================================================================
# 0. 守門員：登入狀態檢查
# =====================================================================
if not st.session_state.get("authenticated", False):
    st.warning("🔒 系統偵測到未授權的存取。請回到登入頁面進行身分驗證。")
    st.stop()

# =====================================================================
# 1. 金鑰與環境設定
# =====================================================================
MY_GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

# =====================================================================
# 2. 資料讀取與清洗引擎 (對接原 GAS 邏輯)
# =====================================================================
def load_portfolio_data(file):
    try:
        if file is not None:
            df = pd.read_excel(file)
        else:
            # 自動尋找副檔名
            file_path_xls = os.path.join("data", "v888測試資料.xls")
            file_path_xlsx = os.path.join("data", "v888測試資料.xlsx")
            if os.path.exists(file_path_xlsx):
                df = pd.read_excel(file_path_xlsx)
            elif os.path.exists(file_path_xls):
                df = pd.read_excel(file_path_xls)
            else:
                return None, "找不到預設資料，請上傳客戶 Excel 檔案。"

        # 依據原 GAS 邏輯：第一列第16欄(Q)是姓名，第17欄(R)是生日
        client_name = str(df.iloc[0, 16]) if df.shape[1] > 16 and pd.notna(df.iloc[0, 16]) else "測試客戶"
        
        current_year = datetime.datetime.now().year
        current_age = 40 # 預設
        if df.shape[1] > 17 and pd.notna(df.iloc[0, 17]):
            birthday_val = df.iloc[0, 17]
            if isinstance(birthday_val, datetime.datetime):
                current_age = current_year - birthday_val.year
            elif isinstance(birthday_val, (int, float)):
                # 如果填民國年
                current_age = current_year - (int(birthday_val) + 1911)

        policies = []
        for i in range(len(df)):
            row = df.iloc[i]
            if pd.isna(row.iloc[1]) or str(row.iloc[1]).strip() == "":
                continue # 空白列跳過
            
            p = {
                "name": str(row.iloc[1]),
                "currency": str(row.iloc[2]) if df.shape[1] > 2 else "TWD",
                "value_now": float(row.iloc[3]) if df.shape[1] > 3 and pd.notna(row.iloc[3]) else 0.0,
                "remark": str(row.iloc[9]) if df.shape[1] > 9 and pd.notna(row.iloc[9]) else "",
                "safetyScore": float(row.iloc[10]) if df.shape[1] > 10 and pd.notna(row.iloc[10]) else 0,
                "yieldScore": float(row.iloc[11]) if df.shape[1] > 11 and pd.notna(row.iloc[11]) else 0,
                "protectionValue": float(row.iloc[12]) if df.shape[1] > 12 and pd.notna(row.iloc[12]) else 0,
                "policyNo": str(row.iloc[18]) if df.shape[1] > 18 and pd.notna(row.iloc[18]) else ""
            }
            policies.append(p)

        return {"clientName": client_name, "currentAge": current_age, "policies": policies}, None

    except Exception as e:
        return None, f"解析 Excel 失敗：{e}"

# =====================================================================
# 3. 側邊欄參數設定
# =====================================================================
st.title("🎯 財富戰情室：退休金準備系統")

st.sidebar.header("📁 資料來源設定")
uploaded_file = st.sidebar.file_uploader("上傳客戶 Excel 資料 (覆蓋預設)", type=["xls", "xlsx"], key="retire_up")

st.sidebar.header("⚙️ 退休規劃參數")
retire_age = st.sidebar.slider("預計退休年齡", 50, 80, 65, key="retire_age")
life_expectancy = st.sidebar.slider("預估餘命 (歲)", 80, 110, 85, key="retire_life")
monthly_spend = st.sidebar.number_input("退休後每月花費 (現值/萬)", value=5.0, step=1.0, key="retire_spend")
inflation = st.sidebar.slider("預期通膨率 (%)", 0.0, 5.0, 2.0, 0.1, key="retire_inf") / 100

st.sidebar.header("📈 預期報酬率設定")
safe_irr = st.sidebar.slider("保本資產預期 IRR (%)", 1.0, 5.0, 2.0, 0.1, key="retire_safe") / 100
risk_irr = st.sidebar.slider("風險資產預期 IRR (%)", 3.0, 15.0, 6.0, 0.5, key="retire_risk") / 100

# =====================================================================
# 4. 資料載入與基礎試算
# =====================================================================
data, error = load_portfolio_data(uploaded_file)

if error:
    st.error(error)
    st.stop()

client_name = data["clientName"]
current_age = data["currentAge"]
policies = data["policies"]
years_to_retire = max(0, retire_age - current_age)
years_in_retire = max(0, life_expectancy - retire_age)

# 計算總資產
total_assets_wan = sum(p["value_now"] for p in policies) / 10000

st.markdown(f"### 🧑‍💼 客戶：**{client_name}** | 目前年齡：**{current_age} 歲** | 距退休：**{years_to_retire} 年**")

# =====================================================================
# 5. 退休缺口精算模組
# =====================================================================
st.subheader("📊 第一階段：退休資金缺口精算")

# 通膨調整後的未來花費
future_monthly_spend = monthly_spend * ((1 + inflation) ** years_to_retire)
total_retire_fund_needed = future_monthly_spend * 12 * years_in_retire

# 現有資產按保本利率增值預估
future_assets_value = total_assets_wan * ((1 + safe_irr) ** years_to_retire)
fund_gap = total_retire_fund_needed - future_assets_value

c1, c2, c3, c4 = st.columns(4)
c1.metric("目前已備總資產", f"{total_assets_wan:,.1f} 萬")
c2.metric("未來每月需花費 (含通膨)", f"{future_monthly_spend:,.1f} 萬")
c3.metric(f"{retire_age}歲時需備妥總額", f"{total_retire_fund_needed:,.1f} 萬")
c4.metric(f"預估退休金缺口", f"{fund_gap:,.1f} 萬", delta_color="inverse" if fund_gap > 0 else "normal")

st.divider()

# =====================================================================
# 6. 資產清單與 AI 戰略分析
# =====================================================================
col_list, col_ai = st.columns([1.2, 1])

with col_list:
    st.subheader("📂 目前持有資產 / 保單清單")
    if policies:
        df_policies = pd.DataFrame(policies)[['name', 'currency', 'value_now', 'protectionValue', 'safetyScore', 'yieldScore']]
        df_policies.columns = ['資產名稱', '幣別', '目前現值', '保障額度', '保本分數', '增值分數']
        st.dataframe(df_policies, use_container_width=True, hide_index=True)
    else:
        st.info("目前無資產資料。")

with col_ai:
    st.subheader("🧠 Gemini 2.5 AI 深度資產健檢")
    if not MY_GEMINI_KEY:
        st.warning("請先於 `.streamlit/secrets.toml` 設定 GEMINI_API_KEY 以解鎖 AI 健檢功能。")
    else:
        st.info("點擊下方按鈕，系統將將此資產組合傳送至 Google 最新的 Gemini 2.5 模型進行深度戰略分析。")
        if st.button("🚀 啟動 AI 戰略分析", use_container_width=True, type="primary"):
            with st.spinner("AI 引擎正在深讀資產結構與評分..."):
                try:
                    client = genai.Client(api_key=MY_GEMINI_KEY)
                    
                    # 將資產資料打包成文字給 AI
                    portfolio_text = "\n".join([
                        f"- {p['name']} (幣別:{p['currency']}) | 現值:{p['value_now']} | 備註:{p['remark']} | 保本分數:{p['safetyScore']} | 增值分數:{p['yieldScore']}" 
                        for p in policies
                    ])
                    
                    prompt = f"""
                    你是一位頂級的 CFP 國際理財規劃顧問。
                    客戶 {client_name} (目前 {current_age} 歲，預計 {retire_age} 歲退休)。
                    預估退休總缺口為 {fund_gap:.1f} 萬。
                    
                    以下是客戶目前的資產清單與評分：
                    {portfolio_text}
                    
                    請以「專業、激勵人心、條理分明」的語氣，直接給出 3 點具體的資產調整建議，幫助他補足退休缺口。
                    (請使用 Markdown 格式，不要廢話，直接切入重點)
                    """
                    
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[prompt]
                    )
                    
                    st.success("✅ AI 分析完成！")
                    st.markdown(f'''
                    <div style="background-color: #f0f7ff; border-left: 5px solid #0052cc; padding: 20px; border-radius: 8px;">
                    {response.text}
                    </div>
                    ''', unsafe_allow_html=True)
                    
                except Exception as e:
                    st.error(f"AI 連線失敗：{e}")

st.divider()

# =====================================================================
# 7. 蒙地卡羅：自存金模擬 (1000次)
# =====================================================================
st.subheader("🎲 第二階段：自存金 1,000 次蒙地卡羅模擬 (補足缺口)")
st.write(f"若要填補 **{fund_gap:,.1f} 萬** 的缺口，並將資金投入 **預期年化 {risk_irr*100:.1f}% / 波動度 12%** 的市場中：")

monthly_saving = st.slider("請設定您願意每月額外提撥的自存金 (萬元)", min_value=0.5, max_value=30.0, value=3.0, step=0.5, key="retire_saving")

if st.button("▶️ 執行 1,000 次未來宇宙模擬", type="primary"):
    with st.spinner("正在運算 1,000 種可能的市場走勢..."):
        sims = 1000
        days = years_to_retire * 12 # 以月為單位
        dt = 1/12
        mu = risk_irr
        vol = 0.12 # 預設市場波動度 12%
        
        # 產生隨機市場波動矩陣
        np.random.seed(42)
        Z = np.random.normal(0, 1, (days, sims))
        monthly_drift = (mu - 0.5 * vol**2) * dt
        monthly_shock = vol * np.sqrt(dt) * Z
        monthly_returns_sim = np.exp(monthly_drift + monthly_shock)
        
        # 累加投資路徑
        paths = np.zeros((days + 1, sims))
        for m in range(1, days + 1):
            # 每月投入 + 上個月本金乘上本月報酬
            paths[m] = (paths[m-1] + monthly_saving) * monthly_returns_sim[m-1]
            
        final_values = paths[-1]
        percentile_5 = np.percentile(final_values, 5)
        percentile_50 = np.percentile(final_values, 50)
        percentile_95 = np.percentile(final_values, 95)
        
        success_rate = np.mean(final_values >= fund_gap) * 100
        
        c_sim1, c_sim2, c_sim3, c_sim4 = st.columns(4)
        c_sim1.metric("達標成功率", f"{success_rate:.1f}%")
        c_sim2.metric("中位數累積 (50%)", f"{percentile_50:,.1f} 萬", f"{percentile_50 - fund_gap:,.1f} 萬" if percentile_50 - fund_gap > 0 else "")
        c_sim3.metric("悲觀情境 (後5%)", f"{percentile_5:,.1f} 萬")
        c_sim4.metric("樂觀情境 (前5%)", f"{percentile_95:,.1f} 萬")
        
        # 繪圖
        fig_mc = go.Figure()
        x_axis = np.arange(current_age, retire_age + 1/12, 1/12)
        
        # 畫 50 條隨機軌跡
        random_indices = np.random.choice(sims, 50, replace=False)
        for i in random_indices:
            fig_mc.add_trace(go.Scatter(
                x=x_axis, y=paths[:, i], mode='lines', 
                line=dict(color='rgba(100, 255, 218, 0.1)', width=1), showlegend=False, hoverinfo='skip'
            ))
            
        # 畫目標線與中位數
        fig_mc.add_trace(go.Scatter(x=x_axis, y=np.percentile(paths, 50, axis=1), name='50% 中位數路徑', line=dict(color='#0052cc', width=3)))
        fig_mc.add_hline(y=fund_gap, line_dash="dash", line_color="#e74c3c", annotation_text=f"🎯 缺口目標: {fund_gap:,.1f}萬", annotation_position="top left")
        
        fig_mc.update_layout(
            title=f"每月提撥 {monthly_saving} 萬之資產增長模擬",
            xaxis_title="年齡", yaxis_title="累積資金 (萬元)",
            template="plotly_dark", hovermode="x unified"
        )
        st.plotly_chart(fig_mc, use_container_width=True)
        
        if success_rate >= 80:
            st.success("🎉 **太棒了！** 依照目前的提撥計畫，您有極高的機率能安穩補足退休缺口！")
        else:
            st.error("⚠️ **計畫警訊**：目前的提撥金額達標機率偏低，建議提高每月自存金額，或與您的 CFP 顧問討論調整資產配置策略。")
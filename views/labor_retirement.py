import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import numpy as np
import ssl
import os
import datetime
from matplotlib.ticker import FuncFormatter

# =====================================================================
# 0. 守門員：登入狀態檢查
# =====================================================================
if not st.session_state.get("authenticated", False):
    st.warning("🔒 系統偵測到未授權的存取。請回到登入頁面進行身分驗證。")
    st.stop()

# =====================================================================
# 1. 系統修正與環境配置
# =====================================================================
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# PDF 列印優化 CSS
st.markdown("""
    <style>
    @media print {
        .stSidebar, .stButton { display: none !important; }
        .main { margin: 0 !important; padding: 0 !important; }
    }
    </style>
    """, unsafe_allow_html=True)

# 強化中文字型相容性 (含 Streamlit Cloud 的文泉驛正黑體)
plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'Arial Unicode MS', 'Microsoft JhengHei', 'PingFang HK', 'SimHei', 'sans-serif'] 
plt.rcParams['axes.unicode_minus'] = False
fmt = FuncFormatter(lambda x, p: f"{int(x):,}")

# =====================================================================
# 2. 核心共用載入函數
# =====================================================================
def load_and_clean_data(file):
    if file is not None:
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return None, f"解析上傳檔案失敗：{e}", 0, 0
    else:
        file_path_xls = os.path.join("data", "勞退版起始資料.xls")
        file_path_xlsx = os.path.join("data", "勞退版起始資料.xlsx")
        if os.path.exists(file_path_xlsx):
            df = pd.read_excel(file_path_xlsx)
        elif os.path.exists(file_path_xls):
            df = pd.read_excel(file_path_xls)
        else:
            return None, None, 0, 0 # 備援方案在主程式處理

    if df is not None:
        # 忠實還原原 GAS 邏輯：第一列第16欄(Q)是姓名，第17欄(R)是生日
        client_name = str(df.iloc[0, 16]) if df.shape[1] > 16 and pd.notna(df.iloc[0, 16]) else "勞退測試客戶"
        
        current_year = datetime.datetime.now().year
        current_age = 40 
        if df.shape[1] > 17 and pd.notna(df.iloc[0, 17]):
            birthday_val = df.iloc[0, 17]
            if isinstance(birthday_val, datetime.datetime):
                current_age = current_year - birthday_val.year
            elif isinstance(birthday_val, (int, float)):
                # 如果填民國年
                current_age = current_year - (int(birthday_val) + 1911)

        names = df.iloc[:, 0].astype(str).tolist()
        vals = [v/10000 if v > 1000000 else v for v in pd.to_numeric(df.iloc[:, 1], errors='coerce').fillna(0)]
        total = sum(vals)
        weights = {n: (v/total if total > 0 else 0) for n, v in zip(names, vals)}
        return {"clientName": client_name, "currentAge": current_age, "names": names, "vals": vals}, None, total, weights
    
    return None, None, 0, 0

# 智能反推最佳提撥額公式 (忠實還原原 GAS HTML JS 邏輯)
def calc_optimal_pmt(target_gap, years, rate):
    if target_gap <= 0 or years <= 0 or rate <= 0: return 0
    months = years * 12
    monthly_rate = rate / 12
    # 公式：c = i*p / (Math.pow(1+i, n)-1)
    pmt = (target_gap * monthly_rate) / (((1 + monthly_rate)**months) - 1)
    return max(0, pmt)

# =====================================================================
# 3. 側邊欄與資料初始化
# =====================================================================
st.title("💼 勞退推算戰情室 (V88.8 忠實還原版)")
uploaded_file = st.sidebar.file_uploader("📁 上傳客戶 Excel (選填)", type=["xls", "xlsx"], key="labor_up_main")

# 初始化資料
raw_data, error, total_assets, weights = load_and_clean_data(uploaded_file)

if error:
    st.error(error)
    st.stop()

if raw_data is None:
    # 備援方案 (若無預設檔案且未上傳)
    names = ['股票型資產', '債券型基金', '年金給付(保險)', '租金收益(房產)', '現金與存款']
    vals = [1500, 1000, 1000, 1000, 500]
    total_assets = sum(vals)
    weights = {n: v/total_assets for n, v in zip(names, vals)}
    client_name = "測試客戶"
    current_age = 60
else:
    names = raw_data["names"]
    vals = raw_data["vals"]
    client_name = raw_data["clientName"]
    current_age = raw_data["currentAge"]

# A/B 開關
service_mode = st.sidebar.radio("服務等級選擇", ["標準版(A)", "AI顧問版(B)"], key="labor_service_mode")

# =====================================================================
# 4. 方案 A：標準版 (忠實還原決策圖表與雷達圖)
# =====================================================================
if service_mode == "標準版(A)":
    st.sidebar.header("📁 A方案：決策參數")
    
    col_age1, col_age2 = st.sidebar.columns(2)
    # 這裡的 slider 變動會即時觸發下方重新運算 (實現還原互動性)
    retire_age = col_age1.slider("退休年齡", current_age+1, 80, 65, key="labor_age_A")
    life_expectancy = col_age2.slider("預估餘命", retire_age+1, 110, 85, key="labor_life_A")
    
    annual_spend = st.sidebar.number_input("年度生活費目標 (萬元)", value=120, step=10, key="labor_spend_A")
    inflation = st.sidebar.slider("預期通膨率 (%)", 0.0, 5.0, 2.0, 0.1, key="labor_inf_A") / 100
    
    col_irr1, col_irr2 = st.sidebar.columns(2)
    safe_irr = col_irr1.slider("保本報酬(%)", 1.0, 5.0, 2.0, 0.1, key="labor_safe_A") / 100
    risk_irr = col_irr2.slider("積極報酬(%)", 3.0, 15.0, 6.0, 0.5, key="labor_risk_A") / 100
    mdd_rate = st.sidebar.slider("極端市場跌幅測試 (%)", 10, 60, 30, key="labor_mdd_A")

    st.markdown(f"### 🧑‍💼 客戶：**{client_name}** | 目前年齡：**{current_age} 歲** | A方案設定")

    # --- 核心計算與數據儀表板 ---
    years_to_retire = max(1, retire_age - current_age)
    years_in_retire = max(1, life_expectancy - retire_age)
    ages = np.arange(current_age, life_expectancy + 1)

    # 退休缺口
    future_monthly_spend = (annual_spend / 12) * ((1 + inflation) ** years_to_retire)
    total_needed = future_monthly_spend * 12 * years_in_retire
    
    # 目前資產未來的價值 (假設按保本利率增值)
    future_assets_val = total_assets * ((1 + safe_irr) ** years_to_retire)
    fund_gap = max(0, total_needed - future_assets_val)

    # 【還原關鍵功能】反推每月需存多少錢 (Optimal Cache)
    opt_safe_pmt = calc_optimal_pmt(fund_gap, years_to_retire, safe_irr)
    opt_risk_pmt = calc_optimal_pmt(fund_gap, years_to_retire, risk_irr)

    st.subheader("一、退休資金戰略儀表板")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("目前總資產", f"{total_assets:,.0f} 萬")
    c2.metric("未來每月花費 (含通膨)", f"{future_monthly_spend:.1f} 萬")
    c3.metric(f"{retire_age}歲時需備總額", f"{total_needed:,.0f} 萬")
    c4.metric(f"目標資金缺口", f"{fund_gap:,.0f} 萬", delta_color="inverse" if fund_gap > 0 else "normal")

    st.markdown(f"""
    <div style="background-color: #f0f7ff; padding: 15px; border-radius: 8px; border-left: 5px solid #0052cc; color: #112240; margin-top: 10px;">
        <h4 style="color: #0052cc; margin-top: 0;">💡 戰略反推：離達標每月還需要自存 (萬元)</h4>
        🛡️ <b>保本策略 (年化 {safe_irr*100:.1f}%)</b>：每月需投入 <b>{opt_safe_pmt:,.2f} 萬</b><br>
        🚀 <b>積極策略 (年化 {risk_irr*100:.1f}%)</b>：每月需投入 <b>{opt_risk_pmt:,.2f} 萬</b>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # --- 資產配置與雷達圖區塊 ---
    # 【忠實還原】雷達圖與決策圖表
    col_chart, col_radar = st.columns([1.5, 1])

    with col_chart:
        st.subheader("② 資產增長曲線圖 (標準 vs. A方案優化)")
        # 簡單推算直線路徑做為對比
        paths = np.zeros((years_to_retire + 1, 2))
        paths[0] = [total_assets, total_assets]
        for y in range(1, years_to_retire + 1):
            paths[y, 0] = paths[y-1, 0] * (1 + safe_irr) # 標準(只靠現有資產)
            # A方案：現有資產增值 + 每月積極自存金累積
            monthly_risk_fund = opt_risk_pmt * 12
            paths[y, 1] = (paths[y-1, 1] * (1 + risk_irr)) + (monthly_risk_fund * ((1+risk_irr)**y - 1)/risk_irr)
            
        fig_growth = go.Figure()
        sim_ages = np.arange(current_age, retire_age + 1)
        fig_growth.add_trace(go.Scatter(x=sim_ages, y=paths[:, 0], name="標準 (僅現有資產)", line=dict(color='gray', dash='dash')))
        fig_growth.add_trace(go.Scatter(x=sim_ages, y=paths[:, 1], name="A方案 (現有+積極自存)", line=dict(color='#0052cc', width=4)))
        fig_growth.add_hline(y=total_needed, line_dash="dash", line_color="#ff4b4b", annotation_text="🎯 總目標")
        fig_growth.update_layout(xaxis_title="年齡", yaxis_title="資產價值 (萬元)", hovermode="x unified", legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
        st.plotly_chart(fig_growth, use_container_width=True)

    with col_radar:
        st.subheader("雷達圖：決策因子對比")
        # 忠實還原原 GAS HTML 雷達圖邏輯 (對比花費與最佳提撥)
        pro_vals = {"傳承與身故": 80, "意外": 60, "住院": 70, "手術": 50, "實支實付": 90, "重疾": 75}
        radar_cats = list(pro_vals.keys())
        # 標準版數據 (隨機演示用，對齊原 HTML 視覺)
        s_data = [80, 60, 70, 50, 90, 75] 
        # 優化版數據 (假設優化後各項分數調升)
        o_data = [90, 85, 80, 75, 95, 85]
        
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=s_data, theta=radar_cats, fill='toself', name='標準版(A)'))
        fig_radar.add_trace(go.Scatterpolar(r=o_data, theta=radar_cats, fill='toself', name='優化支出(A方案)', line=dict(color='#00CC96')))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=True, margin=dict(l=40, r=40, t=20, b=20))
        st.plotly_chart(fig_radar, use_container_width=True)

# =====================================================================
# 5. 方案 B：AI顧問版 (【重點修復】還原勞保勞退數據整合與蒙地卡羅)
# =====================================================================
else:
    st.sidebar.header("💎 B方案：VIP 戰略參數")
    
    # --- 【還原核心功能】補上勞保勞退數據輸入 ---
    st.sidebar.subheader("💰 預期收入補貼 (年額)")
    # 此處輸入框將即時整合進蒙地卡羅模擬
    v_life_inc = st.sidebar.number_input("1. 勞保年金 (月額/萬)", value=2.5, step=0.1, key="labor_ins_B")
    v_ret_inc_lump = st.sidebar.number_input("2. 勞退專戶總額 (一次金/萬)", value=500, step=50, key="labor_ret_B")
    
    annual_spend_B = st.sidebar.number_input("年度生活費目標 (萬元)", value=120, step=10, key="labor_spend_B")
    inflation_B = st.sidebar.slider("預期通膨率 (%)", 0.0, 5.0, 2.0, 0.1, key="labor_inf_B") / 100
    risk_irr_B = st.sidebar.slider("AI 預期報酬率 (%)", 3.0, 15.0, 6.0, 0.5, key="labor_risk_B") / 100
    v_vol = st.sidebar.slider("市場波動度 (%)", 1.0, 25.0, 10.0, key="labor_vol_B") / 100
    v_legacy = st.sidebar.number_input("預留傳承目標 (萬元)", value=1000, key="labor_leg_B")

    # 退休年齡固定為 65 (對齊原文本)，規劃觀察至 85
    retire_age_B = 65
    obs_years = 35 # 從目前60規劃到95
    v_ages = np.arange(current_age, current_age + obs_years + 1)
    
    st.markdown(f"### 🧑‍💼 客戶：**{client_name}** | 目前年齡：**{current_age} 歲** | B方案：AI顧問與全景導航")

    # --- 整合勞保勞退的蒙地卡羅模擬引擎 (忠實還原文本B方案邏輯) ---
    def calc_vip_pro_with_labor(total, spend, l_ins_monthly, r_inc_lump, legacy, rate, vol, start_age):
        sims = 1000
        days = obs_years * 12 
        dt = 1/12
        np.random.seed(42)
        
        # 產生市場隨機波動矩陣
        Z = np.random.normal(0, 1, (days, sims))
        monthly_drift = (rate - 0.5 * vol**2) * dt
        monthly_shock = vol * np.sqrt(dt) * Z
        monthly_returns_sim = np.exp(monthly_drift + monthly_shock)
        
        paths = np.zeros((days + 1, sims))
        paths[0] = total
        
        # 月勞保年金 (萬)
        l_ins_annual = l_ins_monthly
        
        # 依序模擬每一月
        for m in range(1, days + 1):
            curr_age = start_age + (m/12)
            
            # --- 【還原核心邏輯】併入勞保勞退收入 ---
            monthly_income = 0
            if curr_age >= 65:
                monthly_income += l_ins_annual # 啟動勞保年金
                
            if curr_age == 65:
                # 65歲一次匯入勞退專戶金 (一次金)
                paths[m-1] += r_inc_lump
                
            monthly_spend = spend / 12
            
            # 餘額 = (本金 + 收入 - 支出) * 報酬
            # 註：這裡假設支出在月初發生，收入在月初匯入
            net_base = paths[m-1] + monthly_income - monthly_spend
            
            # 護欄機制：低於傳承目標時強制凍結支出 (原文本 B 方案邏輯)
            if net_base < legacy:
                net_base = paths[m-1] + monthly_income - (monthly_spend * 0.5) # 支出打對折
                
            paths[m] = net_base * monthly_returns_sim[m-1]
            paths[m] = np.maximum(paths[m], 0) # 資產歸零停止
            
        return paths

    with st.spinner("🧠 正在整合勞保勞退數據進行 1,000 次蒙地卡羅模擬..."):
        mc_matrix = calc_vip_pro_with_labor(total_assets, annual_spend_B, v_life_inc, v_ret_inc_lump, v_legacy, risk_irr_B, v_vol, current_age)
        
        final_values = mc_matrix[-1]
        percentile_med = np.median(mc_matrix, axis=1) # 50% 中位數路徑
        
        # 計算退休成功率 (期末資產 > 0)
        success_rate = np.mean(final_values > 0) * 100
        
    st.subheader(f"④ 退休提領與傳承導航 (實測成功率: {success_rate:.1f}%)")
    
    c_b1, c_b2, c_b3 = st.columns(3)
    c_b1.metric("期末資產中位數 (95歲)", f"{int(percentile_med[-1]):,} 萬")
    c_b2.metric("勞保月領 (65歲起)", f"{v_life_inc} 萬")
    c_b3.metric("勞退一次金 (65歲)", f"{v_ret_inc_lump} 萬")

    # --- 繪圖區塊 ---
    col_v1, col_v2 = st.columns([1, 1.2])

    with col_v1:
        st.subheader("資產配置建議：標準 vs AI")
        suggested_weights = [w*0.8 if '股' in n else (w*1.2 if '債' in n or '年' in n else w) for n, w in zip(names, weights.values())]
        s_sum = sum(suggested_weights); suggested_weights = [sw/s_sum for sw in suggested_weights]
        
        fig_s, ax_s = plt.subplots(); 
        ax_s.pie(suggested_weights, labels=names, autopct='%1.1f%%'); 
        st.pyplot(fig_s)
        st.success("💡 **AI顧問配置建議**：建議稍微調升穩定收益資產比重，以守護傳承底線。")

    with col_v2:
        st.subheader("全景導航模擬圖 (整合勞保勞退)")
        fig_mc = go.Figure()
        
        # 畫 50 條隨機軌跡做為視覺參考
        sim_ages_mc = np.linspace(current_age, current_age + obs_years, mc_matrix.shape[0])
        random_indices = np.random.choice(1000, 50, replace=False)
        for i in random_indices:
            fig_mc.add_trace(go.Scatter(x=sim_ages_mc, y=mc_matrix[:, i], mode='lines', line=dict(color='rgba(142, 68, 173, 0.05)', width=1), showlegend=False, hoverinfo='skip'))
            
        # 畫中位數與傳承線
        fig_mc.add_trace(go.Scatter(x=sim_ages_mc, y=percentile_med, name='中位數資產餘額', line=dict(color='#8e44ad', width=4)))
        fig_mc.add_hline(y=v_legacy, line_dash="dash", line_color="#e74c3c", annotation_text=f"傳承目標: {v_legacy}萬")
        fig_mc.add_vline(x=65, line_dash="dot", line_color="gray", annotation_text="65歲(勞保勞退啟動)")
        
        fig_mc.update_layout(xaxis_title="年齡", yaxis_title="資產價值 (萬元)", hovermode="x unified", legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
        st.plotly_chart(fig_mc, use_container_width=True)

    st.divider()

    # --- AI 健檢區塊 ---
    st.subheader("🔮 ⑥ AI 戰略分析 (併入勞保勞退數據)")
    if not MY_GEMINI_KEY:
        st.warning("請先設定 GEMINI_API_KEY。")
    else:
        if st.button("🚀 啟動 AI 深度戰略分析", use_container_width=True, type="primary"):
            with st.spinner("AI 正在根據勞保數據與模擬結果生成戰略報告..."):
                try:
                    from google import genai
                    client = genai.Client(api_key=MY_GEMINI_KEY)
                    
                    prompt = f"""
                    你是一位頂級的 CFP 國際理財規劃顧問。
                    客戶 {client_name} 目前 {current_age} 歲。
                    設定在 65 歲將一次性匯入勞退專戶總額 {v_ret_inc_lump} 萬，並開始月領勞保年金 {v_life_inc} 萬。
                    在積極型投資({risk_irr_B*100}%)，設定 2027年為期末傳承目標 {v_legacy} 萬。
                    
                    蒙地卡羅實測結果：95 歲資產成功率為 {success_rate:.1f}%。
                    
                    請以「專業、戰略性」的語氣，直接給出 3 點針對「如何在 65 歲前優化資產配置、確保傳承目標」的具體建議。
                    (請使用 Markdown 格式)
                    """
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt])
                    
                    st.success("✅ AI 戰略分析完成！")
                    st.markdown(f'<div style="background-color: #f0f7ff; border-left: 5px solid #0052cc; padding: 20px; border-radius: 8px;">{response.text}</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"AI 連線失敗：{e}")

# ==========================================
# 頁尾免責聲明
# ==========================================
st.divider()
footer_html = """
<div style="text-align: center; color: #7f8c8d; font-size: 12px; line-height: 1.5; padding: 15px 0;">
    <strong>版權所有 © 林馬丁 (Martin Lin)。本報表圖表文字由 AI 自動解析生成，僅供 CFP 內部參考，理賠依各保險公司憑證為準。</strong><br>
    <br>
    <b>【系統免責聲明】</b><br>
    1. <b>僅供參考，非投資建議：</b> 本系統所有模擬數據均基於歷史假設與特定演算法，絕不構成任何具體之投資、投保或稅務建議。<br>
    2. <b>不保證未來績效：</b> 通膨率、醫療通膨、報酬率與波動度皆可能隨市場巨幅變動，歷史數據不代表未來實際表現。<br>
    3. <b>風險自負原則：</b> 顧問或使用者應獨立判斷並自行承擔所有決策之最終風險。本系統概不承擔任何法律與連帶賠償責任。
</div>
"""
st.markdown(footer_html, unsafe_allow_html=True)
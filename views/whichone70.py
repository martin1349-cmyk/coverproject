import streamlit as st
import pandas as pd
import math

# ==========================================
# 0. 守門員：登入狀態檢查
# ==========================================
if not st.session_state.get("authenticated", False):
    st.warning("🔒 系統偵測到未授權的存取。請回到登入頁面進行身分驗證。")
    st.stop()

# ==========================================
# 1. 側邊欄：參數設定 (加入 key 進行變數隔離)
# ==========================================
st.sidebar.header("⚙️ 決策參數設定")

st.sidebar.subheader("1. 薪資與年資變數")
# 嚴格依循勞工保險投保薪資分級表 (11級)
salary_options = [29500, 30300, 31800, 33300, 34800, 36300, 38200, 40100, 42000, 43900, 45800]

avg_salary_60 = st.sidebar.select_slider(
    "變數A：最高60個月平均薪資", 
    options=salary_options, 
    value=45800,
    help="勞保局計算退休金的基準 (法定級距)",
    key="whichone70_avg_salary_60"
)

current_salary = st.sidebar.select_slider(
    "變數B：目前實際投保薪資", 
    options=salary_options, 
    value=29500,
    help="決定延後退休期間每個月要繳多少保費 (法定級距)",
    key="whichone70_current_salary"
)

base_years = st.sidebar.number_input(
    "60歲時已累積年資 (年)", 
    min_value=15, max_value=50, value=30,
    key="whichone70_base_years"
)

st.sidebar.subheader("2. 單一情境模擬變數 (連動頁籤1)")
target_age = st.sidebar.slider(
    "計畫延後請領年紀", 61, 70, 65,
    key="whichone70_target_age"
)
ins_type = st.sidebar.radio(
    "60歲後續保身份", ("公司投保", "職業工會"),
    key="whichone70_ins_type"
)

# ==========================================
# 2. 核心運算模組 (單一情境)
# ==========================================
if ins_type == "公司投保":
    monthly_cost = current_salary * 0.12 * 0.20  
else:
    monthly_cost = current_salary * 0.11 * 0.60  

delayed_years = target_age - 60
delayed_months = delayed_years * 12
total_premium_cost = monthly_cost * delayed_months

# 方案 A (60歲)
monthly_A = avg_salary_60 * base_years * 0.0155 * 0.80

# 方案 B (延後請領)
years_B = base_years + delayed_years
ratio_B = 1 + (target_age - 65) * 0.04  
monthly_B = avg_salary_60 * years_B * 0.0155 * ratio_B

# 財務缺口計算
opportunity_cost = monthly_A * delayed_months 
total_catch_up = opportunity_cost + total_premium_cost 
monthly_advantage = monthly_B - monthly_A 

if monthly_advantage > 0:
    years_to_breakeven = total_catch_up / (monthly_advantage * 12)
    exact_breakeven_age = target_age + years_to_breakeven
else:
    years_to_breakeven = float('inf')
    exact_breakeven_age = None

# 模擬至 100 歲的數據矩陣
data = []
cum_A = 0
cum_B = 0 
for age in range(60, 101): # 延展至 100 歲
    cum_A += monthly_A * 12
    if age < target_age:
        cum_B -= monthly_cost * 12
    else:
        cum_B += monthly_B * 12

    data.append({
        "年齡": age,
        "方案A (60歲領) 累計金額": round(cum_A),
        f"方案B ({target_age}歲領) 累計金額": round(cum_B),
        "當年度累計總差額": round(cum_B - cum_A)
    })
df_trend = pd.DataFrame(data)

# ==========================================
# 3. 建立畫面與頁籤
# ==========================================
st.title("🧮 退休族勞保請領決策系統 (法定級距專業版)")
tab1, tab2 = st.tabs(["📊 單一情境總結與趨勢 (至100歲)", "🗓️ 各歲數全情境打平年限表"])

# === 頁籤 1 內容 ===
with tab1:
    col1, col2, col3 = st.columns(3)
    col1.metric("方案 A (60歲起領) 月額", f"${round(monthly_A):,}", "基準")
    col2.metric(f"方案 B ({target_age}歲起領) 月額", f"${round(monthly_B):,}", f"每月多領 ${round(monthly_advantage):,}")
    col3.metric(f"延後{delayed_years}年保費總支出", f"${round(total_premium_cost):,}", f"月繳 ${round(monthly_cost):,} (依變數B)", delta_color="inverse")

    st.subheader("⚠️ 延後請領的「真實財務缺口」")
    st.error(f"**總追趕差額高達：${round(total_catch_up):,}**")
    st.markdown(f"""
    * **機會成本 (少領的年金)**：`${round(monthly_A):,} × {delayed_months} 個月 = ${round(opportunity_cost):,}`
    * **實質支出 (多繳的保費)**：`${round(monthly_cost):,} × {delayed_months} 個月 = ${round(total_premium_cost):,}`
    
    💡 **回本時間試算**：您從 {target_age} 歲起，每個月多領的 **${round(monthly_advantage):,}**，需要連續領取 **{round(years_to_breakeven, 1)} 年**，也就是必須活到 **{math.ceil(exact_breakeven_age) if exact_breakeven_age else '無法打平'} 歲**，總資產才會真正超越 60 歲退的方案！
    """)

    st.divider()
    st.subheader("📈 60至100歲累計金額變化趨勢圖")
    st.line_chart(df_trend.set_index("年齡")[["方案A (60歲領) 累計金額", f"方案B ({target_age}歲領) 累計金額"]])

    with st.expander("展開查看 60-100 歲詳細數據變化表"):
        # 套用新語法 use_container_width=True
        st.dataframe(df_trend.style.format("{:,}"), use_container_width=True)

# === 頁籤 2 內容 ===
with tab2:
    st.subheader("🗓️ 全情境打平年齡矩陣表 (比較 61~70 歲請領)")
    st.markdown("此表自動計算延後至各年紀請領的「真實回本年紀」，並以國人平均預期壽命 **85 歲** 為基準，為您試算出長期累積的總淨額（已扣除保費成本）。")
    
    matrix_data = []
    
    # 針對 61 到 70 歲進行全運算
    for t_age in range(61, 71):
        row_data = {"計畫請領年紀": f"{t_age} 歲"}
        d_years = t_age - 60
        d_months = d_years * 12
        y_B = base_years + d_years
        r_B = 1 + (t_age - 65) * 0.04
        m_B = avg_salary_60 * y_B * 0.0155 * r_B
        opp_cost = monthly_A * d_months
        m_adv = m_B - monthly_A
        
        # 預期壽命 85 歲的領取月數 (若請領年紀超過 85，則以 0 計算)
        months_to_85 = (85 - t_age) * 12 if 85 > t_age else 0
        
        # 運算: 公司投保
        cost_company = current_salary * 0.12 * 0.20
        total_p_company = cost_company * d_months
        catch_up_company = opp_cost + total_p_company
        # 計算 85 歲總淨額 = (月領額 * 活到85歲的領取月數) - 延後期間多付的總保費
        net_total_85_comp = (m_B * months_to_85) - total_p_company
        
        if m_adv > 0:
            be_company = t_age + (catch_up_company / (m_adv * 12))
            row_data["公司投保-打平年齡"] = f"{be_company:.1f} 歲"
        else:
            row_data["公司投保-打平年齡"] = "無法打平"
        row_data["公司投保-85歲累計總額"] = f"${round(net_total_85_comp):,}"
            
        # 運算: 職業工會
        cost_union = current_salary * 0.11 * 0.60
        total_p_union = cost_union * d_months
        catch_up_union = opp_cost + total_p_union
        # 計算 85 歲總淨額 = (月領額 * 活到85歲的領取月數) - 延後期間多付的總保費
        net_total_85_union = (m_B * months_to_85) - total_p_union
        
        if m_adv > 0:
            be_union = t_age + (catch_up_union / (m_adv * 12))
            row_data["職業工會-打平年齡"] = f"{be_union:.1f} 歲"
        else:
            row_data["職業工會-打平年齡"] = "無法打平"
        row_data["職業工會-85歲累計總額"] = f"${round(net_total_85_union):,}"
            
        matrix_data.append(row_data)
        
    df_matrix = pd.DataFrame(matrix_data)
    
    # 隱藏預設 index，並套用新語法 use_container_width=True
    st.dataframe(df_matrix.set_index("計畫請領年紀"), use_container_width=True)

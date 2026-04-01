import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import math
import os

# =====================================================================
# 0. 守門員：登入狀態檢查 (整合系統專用驗證機制)
# =====================================================================
if not st.session_state.get("authenticated", False):
    st.warning("🔒 系統偵測到未授權的存取。請回到登入頁面進行身分驗證。")
    st.stop()

# ==========================================
# 1. 頁面與全域風格設定
# ==========================================
# st.set_page_config(page_title="V88.8 退休推算戰情室", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* 強制深色背景與字體顏色還原 */
    .stApp { background-color: #0a192f !important; color: #e6f1ff !important; font-family: 'Noto Sans TC', sans-serif; }
    
    /* 調整指標字體 */
    [data-testid="stMetricValue"] { color: #64ffda !important; font-family: monospace !important; font-size: 28px !important; font-weight: bold;}
    [data-testid="stMetricLabel"] { color: #8892b0 !important; font-size: 14px !important; font-weight: bold; }
    
    /* 調整區塊背景 */
    .st-emotion-cache-1wivap2 { background-color: #112240; border-radius: 12px; padding: 15px; border: 1px solid #233554; }
    
    /* 進度條與卡片樣式 */
    .progress-box { background: #0a192f; border-radius: 10px; padding: 10px; border: 1px solid #233554; margin: 10px 0; }
    .progress-bar-bg { background: #233554; height: 10px; border-radius: 5px; overflow: hidden; width: 100%; }
    .advice-card { background: rgba(10, 25, 47, 0.8); border: 1px solid #233554; border-left: 6px solid #64ffda; border-radius: 8px; padding: 15px; margin: 15px 0; }
    
    /* 分隔線 */
    hr { border-color: #233554 !important; margin: 15px 0 !important; }
    
    /* 按鈕樣式 */
    .btn-apply-safe > button { background-color: #06d6a0 !important; color: #0a192f !important; font-weight: bold !important; border-radius: 4px; }
    .btn-apply-risk > button { background-color: #ffd166 !important; color: #0a192f !important; font-weight: bold !important; border-radius: 4px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 初始化 Session State
# ==========================================
default_states = {
    'current_view': 'dashboard',
    'client_name': '等待匯入...',
    'current_age': 57,
    'policies': [],
    
    # --- 共通參數 ---
    'retire_age': 65,
    'target_goal': 13000000,
    'expect_pension': 50000,
    
    # --- 戰情室專用 ---
    'acc_rate': 5.0,
    'wdr_rate': 1.0,
    'annual_income': 678132,
    
    # --- 模擬器專用 ---
    'avg_ins_salary': 45800,
    'years_li': 30,
    'current_lp': 1000000,
    'current_salary': 30000,
    'has_self_contrib': True,
    'lp_rate': 4.0,
    'sim_mu': 1.0
}
for key, val in default_states.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ==========================================
# 3. 核心回呼函式 Callbacks
# ==========================================
def switch_view(view_name):
    st.session_state.current_view = view_name

def apply_ai_suggestion(suggested_value):
    st.session_state.expect_pension = suggested_value

# ==========================================
# 4. 數學邏輯運算
# ==========================================
def parse_excel(df):
    if len(df) < 2: return
    row1 = df.iloc[1].fillna('')
    st.session_state.client_name = row1[16] if row1[16] != '' else "尊榮客戶"
    
    birthday_val = row1[17]
    if isinstance(birthday_val, (int, float)) and birthday_val > 0:
        excel_epoch = pd.Timestamp('1899-12-30')
        actual_birthday = excel_epoch + pd.to_timedelta(birthday_val, unit='D')
        today = pd.Timestamp.today()
        age = today.year - actual_birthday.year
        if today.month < actual_birthday.month or (today.month == actual_birthday.month and today.day < actual_birthday.day):
            age -= 1
        st.session_state.current_age = age

    policies = []
    for i in range(1, len(df)):
        row = df.iloc[i].fillna(0)
        if row[1] == 0 or str(row[1]).strip() == '': continue
        policy = {
            'policyNo': row[18], 'name': row[1], 'currency': row[2],
            'values': [float(row[3]), float(row[4]), float(row[5]), float(row[6]), float(row[7]), float(row[8])],
            'safetyScore': float(row[10]) if row[10] else 8,
            'yieldScore': float(row[11]) if row[11] else 5,
            'protectionValue': float(row[12]) if row[12] else 0,
            'totalTerms': float(row[13]) if row[13] else 20,
            'paidYears': float(row[14]) if row[14] else 0
        }
        policies.append(policy)
    st.session_state.policies = policies

def calculate_dashboard_metrics():
    target = st.session_state.target_goal
    a_rate = st.session_state.acc_rate / 100
    w_rate = st.session_state.wdr_rate / 100
    expect_pmt = st.session_state.expect_pension
    r_age = st.session_state.retire_age
    yR = max(0, r_age - st.session_state.current_age)

    total_R, sum_S, sum_Y, total_Prot, weighted_Liq = 0, 0, 0, 0, 0
    for p in st.session_state.policies:
        v = p['values']
        val_at_retire = 0
        if yR <= 1: val_at_retire = v[0]
        elif yR <= 10: val_at_retire = v[0] + (v[1]-v[0])*((yR-1)/9)
        else:
            decade = math.floor(yR/10)
            idx1 = min(4, decade)
            idx2 = min(5, decade+1)
            val_at_retire = v[idx1] + (v[idx2]-v[idx1])*((yR%10)/10)
        
        v_retire = val_at_retire * (30 if p['currency'] == 'USD' else 1)
        total_R += v_retire
        sum_S += p['safetyScore']
        sum_Y += p['yieldScore']
        total_Prot += (p['protectionValue'] * (30 if p['currency'] == 'USD' else 1))
        weighted_Liq += (min(1, p['paidYears'] / max(1, p['totalTerms'])) * v_retire)

    m_acc_rate = a_rate / 12
    gap = max(0, target - total_R)
    monthly_save = 0
    if gap > 0 and yR > 0:
        if m_acc_rate <= 0: monthly_save = gap / (yR * 12)
        else: monthly_save = gap / ((math.pow(1 + m_acc_rate, yR * 12) - 1) / m_acc_rate)

    m_wdr_rate = w_rate / 12
    sim_w_rate = max(0.00001, m_wdr_rate)
    if expect_pmt <= target * sim_w_rate: lon_text = "永續領取"
    else:
        denom = expect_pmt - (target * sim_w_rate)
        if denom > 0:
            n = math.log(expect_pmt / denom) / math.log(sim_w_rate + 1)
            lon_text = f"{math.floor(r_age + (n / 12))} 歲"
        else:
            lon_text = f"{r_age + 1} 歲 (立即耗盡)"
            
    avg_s = sum_S / max(1, len(st.session_state.policies)) if st.session_state.policies else 0
    avg_y = sum_Y / max(1, len(st.session_state.policies)) if st.session_state.policies else 0
    ach_sc = min(10, (total_R/target)*10) if target > 0 else 0
    prot_sc = min(10, (total_Prot / (st.session_state.annual_income * 10)) * 10) if st.session_state.annual_income else 0
    liq_sc = (weighted_Liq / max(1, total_R)) * 10 if total_R > 0 else 0
    achieve_percent = min(100, (total_R / target) * 100) if target > 0 else 0
            
    return total_R, gap, monthly_save, lon_text, avg_s, avg_y, ach_sc, prot_sc, liq_sc, yR, achieve_percent

# 🚀 升級版：Numpy 向量化運算與二元搜尋法 (將自備本金完美納入精算)
def run_monte_carlo():
    ageNow = st.session_state.current_age
    ageRetire = min(st.session_state.retire_age, 70)
    avgInsSalary = min(st.session_state.avg_ins_salary, 45800)
    yearsLI = st.session_state.years_li
    currentLP = st.session_state.current_lp
    currentSalary = st.session_state.current_salary
    hasSelf = st.session_state.has_self_contrib
    lpRate = st.session_state.lp_rate / 100
    capital = st.session_state.target_goal  
    mu = st.session_state.sim_mu / 100
    sigma = 0.07
    inputSpend = st.session_state.expect_pension
    
    diff = ageRetire - 65
    factor = max(0.8, min(1.2, 1 + (diff * 0.04)))
    liMonth = round(avgInsSalary * yearsLI * 0.0155 * factor)
    
    yearsToRetire = max(0, ageRetire - ageNow)
    contribRate = 0.12 if hasSelf else 0.06
    lpContrib = min(currentSalary, 150000) * contribRate
    
    if lpRate == 0: lpFuture = currentLP + (lpContrib * 12 * yearsToRetire)
    else: lpFuture = currentLP * math.pow(1 + lpRate, yearsToRetire) + (lpContrib * 12 * ((math.pow(1 + lpRate, yearsToRetire) - 1) / lpRate))
        
    termYears = 85 - ageRetire
    lpMonth = 0
    if termYears > 0:
        rMonth = mu / 12
        nMonth = termYears * 12
        if rMonth == 0: lpMonth = lpFuture / nMonth
        else: lpMonth = (lpFuture * rMonth) / (1 - math.pow(1 + rMonth, -nMonth))
        
    baseIncome = liMonth + round(lpMonth)
    effectiveSpend = max(inputSpend, baseIncome)
    simYears = 100 - ageRetire
    
    if simYears <= 0:
        return baseIncome, {80:10, 85:10, 90:10, 95:10, 100:10}, [], baseIncome, baseIncome

    # --- Numpy 矩陣運算核心 ---
    np.random.seed(42) # 固定隨機種子，確保介面數字穩定
    returns = mu + sigma * np.random.normal(0, 1, (simYears, 1000))
    incomes = np.array([baseIncome if (ageRetire + y + 1) <= 85 else liMonth for y in range(simYears)])
    
    # 1. 計算使用者當前設定的勝率與軌跡
    balances = np.full(1000, float(capital))
    paths = np.zeros((simYears + 1, 1000))
    paths[0] = balances
    gaps = np.maximum(0, effectiveSpend - incomes) * 12
    
    alives = {age: np.full(1000, ageRetire >= age) for age in [80, 85, 90, 95, 100]}
    
    for y in range(simYears):
        age = ageRetire + y + 1
        balances = balances * (1 + returns[y]) - gaps[y]
        balances = np.maximum(balances, 0)
        paths[y+1] = balances
        
        for check_age in alives.keys():
            if age == check_age:
                alives[check_age] = (balances > 0)
                
    counts = {age: int(np.sum(alives[age])) for age in alives.keys()}
    trajectories = paths[:, :50].T.tolist()
    
    # 2. 逆向二元搜尋引擎：精準反推自備本金(Capital)在特定勝率下的極限提領額
    def get_win_rate(test_spend):
        test_gaps = np.maximum(0, test_spend - incomes) * 12
        test_b = np.full(1000, float(capital))
        for y in range(simYears):
            test_b = test_b * (1 + returns[y]) - test_gaps[y]
            test_b = np.maximum(test_b, 0)
        return np.sum(test_b > 0) / 10.0
        
    def find_optimal_spend(target_rate):
        if capital <= 0: return baseIncome
        low = float(baseIncome)
        # 上限：基底收入 + 每年領回本金 + 最高預期報酬 (極限寬鬆範圍)
        high = float(baseIncome + (capital / 12) + (capital * max(0, mu)))
        best = baseIncome
        
        if get_win_rate(baseIncome) < target_rate: return baseIncome
            
        for _ in range(20): # 20次逼近運算足以精準定位到個位數
            mid = (low + high) / 2
            if get_win_rate(mid) >= target_rate:
                best = mid
                low = mid # 勝率達標，挑戰提領更多錢
            else:
                high = mid # 勝率不夠，減少提領額
        return math.floor(best)
        
    optimalSafeCache = find_optimal_spend(80.0)
    optimalRiskCache = find_optimal_spend(50.0)
    
    return baseIncome, counts, trajectories, optimalSafeCache, optimalRiskCache

# ==========================================
# 5. 資料載入函數 (精準補回 header=None)
# ==========================================
@st.cache_data(show_spinner=False)
def load_data(file_buffer):
    if file_buffer is not None:
        try:
            return pd.read_excel(file_buffer, header=None)
        except Exception as e:
            st.error(f"上傳檔案解析失敗: {e}")
            st.stop()
    else:
        possible_paths = [
            os.path.join("data", "labor_test.xlsx"),
            os.path.join("data", "勞退版測試資料.xlsx"),
            os.path.join("data", "勞退版起始資料.xls")
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return pd.read_excel(path, header=None)
        
        st.warning("⚠️ 系統找不到預設資料檔案 (可能 GitHub 尚未同步)。請由左側手動上傳客戶 Excel 檔案。")
        st.stop()

# ==========================================
# 6. 側邊欄：統一所有變數輸入區塊 
# ==========================================
with st.sidebar:
    st.markdown("<h3 style='color:#64ffda;text-align:center;'>⚙️ 系統控制面板</h3>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("📁 上傳客戶 Excel (選填)", type=["xls", "xlsx"])

# 👉 執行資料載入並防護
df = load_data(uploaded_file)
if df is None:
    st.stop()

# 👉 解析資料並存入 session_state
parse_excel(df)

with st.sidebar:
    st.markdown("---")
    
    if st.session_state.current_view == 'dashboard':
        st.button("🚀 啟動 AI 退休模擬器", type="primary", use_container_width=True, on_click=switch_view, args=('simulation',))
    else:
        st.button("❌ 返回戰情室", type="primary", use_container_width=True, on_click=switch_view, args=('dashboard',))
        
    st.markdown("---")
    
    st.markdown("<div style='color:#64ffda;font-size:14px;font-weight:bold;margin-bottom:8px;'>🎯 核心目標設定</div>", unsafe_allow_html=True)
    st.session_state.retire_age = st.number_input("退休年齡", value=int(st.session_state.retire_age), min_value=1, step=1)
    st.session_state.target_goal = st.number_input("目標金額 (TWD)", value=int(st.session_state.target_goal), min_value=0, step=100000)
    st.session_state.expect_pension = st.number_input("退休後每月提領 (TWD)", value=int(st.session_state.expect_pension), min_value=0, step=5000)

    st.markdown("---")

    if st.session_state.current_view == 'dashboard':
        st.markdown("<div style='color:#64ffda;font-size:14px;font-weight:bold;margin-bottom:8px;'>📈 戰情室專用參數</div>", unsafe_allow_html=True)
        st.session_state.acc_rate = st.number_input("累積報酬(%)", value=float(st.session_state.acc_rate), step=0.1, format="%.1f")
        st.session_state.wdr_rate = st.number_input("提領生息(%)", value=float(st.session_state.wdr_rate), step=0.1, format="%.1f")
        st.session_state.annual_income = st.number_input("年收入估算 (TWD)", value=int(st.session_state.annual_income), min_value=0, step=10000)
    
    elif st.session_state.current_view == 'simulation':
        st.markdown("<div style='color:#64ffda;font-size:14px;font-weight:bold;margin-bottom:8px;'>🤖 AI 模擬器基礎參數</div>", unsafe_allow_html=True)
        st.session_state.avg_ins_salary = st.number_input("勞保投保薪資 (Max 45,800)", value=int(st.session_state.avg_ins_salary), min_value=0, max_value=45800, step=1000)
        st.session_state.years_li = st.number_input("勞保年資", value=int(st.session_state.years_li), min_value=0, step=1)
        st.session_state.current_lp = st.number_input("勞退目前累積", value=int(st.session_state.current_lp), min_value=0, step=10000)
        st.session_state.current_salary = st.number_input("勞退提撥月薪", value=int(st.session_state.current_salary), min_value=0, step=1000)
        st.session_state.has_self_contrib = st.checkbox("勞退自提 6% ?", value=st.session_state.has_self_contrib)
        st.session_state.lp_rate = st.number_input("勞退預期績效 (%)", value=float(st.session_state.lp_rate), step=0.1, format="%.1f")
        st.session_state.sim_mu = st.number_input("自存金提領期報酬(μ%)", value=float(st.session_state.sim_mu), step=0.1, format="%.1f")
        
        if st.button("🔄 重新運算模擬", use_container_width=True):
            st.rerun()

# ==========================================
# 7. 主畫面：戰情室 (Dashboard)
# ==========================================
if st.session_state.current_view == 'dashboard':
    st.markdown("<h2 style='text-align:center;color:#64ffda;margin-top:0;'>📊 退休推算戰情室</h2>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"<div style='background:rgba(100,255,218,0.05);padding:8px;border-radius:20px;text-align:center;border:1px solid rgba(100,255,218,0.1);color:#8892b0;'>客戶：<span style='color:#64ffda;font-weight:bold;'>{st.session_state.client_name}</span></div>", unsafe_allow_html=True)
    c2.markdown(f"<div style='background:rgba(100,255,218,0.05);padding:8px;border-radius:20px;text-align:center;border:1px solid rgba(100,255,218,0.1);color:#8892b0;'>現齡：<span style='color:#64ffda;font-weight:bold;'>{st.session_state.current_age} 歲</span></div>", unsafe_allow_html=True)
    c3.markdown(f"<div style='background:rgba(100,255,218,0.05);padding:8px;border-radius:20px;text-align:center;border:1px solid rgba(100,255,218,0.1);color:#8892b0;'>退休倒數：<span style='color:#64ffda;font-weight:bold;'>{max(0, st.session_state.retire_age - st.session_state.current_age)} 年</span></div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    total_R, gap, monthly_save, lon_text, avg_s, avg_y, ach_sc, prot_sc, liq_sc, yR, achieve_percent = calculate_dashboard_metrics()
    
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.metric(f"{st.session_state.retire_age} 歲預計總資產", f"${round(total_R):,}")
        st.markdown(f"<div style='color:#64ffda;font-size:13px;margin-top:-15px;'>{st.session_state.wdr_rate:.1f}% 生息：${round((st.session_state.target_goal * (st.session_state.wdr_rate/100))/12):,}/月</div>", unsafe_allow_html=True)
    with m_col2:
        st.markdown(f"<div style='color:#8892b0;font-size:14px;font-weight:bold;margin-bottom:5px;'>達成缺口需月存額</div><div style='color:#ef476f;font-family:monospace;font-size:28px;font-weight:bold;'>${round(monthly_save):,}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='color:#ffd166;font-size:13px;'>可支領至：{lon_text}</div>", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    
    st.markdown("<div style='font-weight:bold;font-size:16px;color:#e6f1ff;margin-bottom:10px;'>📈 資產累積趨勢</div>", unsafe_allow_html=True)
    fig_asset = go.Figure()
    COLORS = ['rgba(100,255,218,0.8)', 'rgba(17,138,178,0.8)', 'rgba(255,209,102,0.8)', 'rgba(239,71,111,0.8)', 'rgba(6,214,160,0.8)', 'rgba(114,9,183,0.8)']
    x_labels = ['0年','10年','20年','30年','40年','50年','60年']
    
    cum_vals = [0]*7
    for idx, p in enumerate(st.session_state.policies):
        vals = [0] + p['values']
        layer = []
        for j, v in enumerate(vals):
            val_twd = v * (30 if p['currency'] == 'USD' else 1)
            cum_vals[j] += val_twd
            layer.append(cum_vals[j])
        fig_asset.add_trace(go.Scatter(x=x_labels, y=layer, mode='lines', fill='tonexty', 
                                       name=p['name'], line=dict(width=0), fillcolor=COLORS[idx % 6]))
    
    fig_asset.add_trace(go.Scatter(x=x_labels, y=[st.session_state.target_goal]*7, mode='lines', 
                                   name='退休目標', line=dict(color='#ff4d4d', width=3)))
    
    comp_data = []
    r = st.session_state.acc_rate / 100
    ann_spend = st.session_state.expect_pension * 12
    present_val = total_R / math.pow(1+r, yR) if (1+r) > 0 else total_R
    for t in range(0, 61, 10):
        if t <= yR: comp_data.append(present_val * math.pow(1+r, t))
        else:
            post = t - yR
            bal = total_R
            for _ in range(post):
                bal = bal * (1+r) - ann_spend
                if bal < 0: bal = 0
            comp_data.append(bal)
            
    fig_asset.add_trace(go.Scatter(x=x_labels, y=comp_data, mode='lines', 
                                   name='累積預測(含提領)', line=dict(color='#ffd166', width=2)))
    
    fig_asset.update_layout(height=450, margin=dict(l=0,r=0,t=20,b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            legend=dict(font=dict(color='#fff', size=12)),
                            xaxis=dict(gridcolor='#233554', tickfont=dict(color='#fff')),
                            yaxis=dict(gridcolor='#233554', tickfont=dict(color='#fff')))
    st.plotly_chart(fig_asset, use_container_width=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    
    st.markdown("<div style='font-weight:bold;font-size:16px;color:#e6f1ff;margin-bottom:10px;'>🎯 退休體質五維度與達成率</div>", unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="progress-box">
        <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:5px; color:#8892b0;">
            <span>既有達成率</span><span style="color:#64ffda;font-weight:bold;">{round(achieve_percent)}%</span>
        </div>
        <div class="progress-bar-bg">
            <div style="width:{achieve_percent}%; background:#118ab2; height:100%; border-radius:5px;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    radar_col, score_col = st.columns([2, 1])
    with radar_col:
        fig_radar = go.Figure(data=go.Scatterpolar(
            r=[avg_s, avg_y, ach_sc, prot_sc, liq_sc],
            theta=['安全性','獲利性','達成率','保障度','流動性'],
            fill='toself',
            fillcolor='rgba(100,255,218,0.3)',
            line=dict(color='#64ffda', width=2)
        ))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=False, range=[0, 10]), bgcolor='rgba(0,0,0,0)'),
                                showlegend=False, height=350, margin=dict(l=40,r=40,t=20,b=20), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_radar, use_container_width=True)
        
    with score_col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(f"""
        <table style="width:100%; border-collapse:collapse; font-size:14px; color:#8892b0;">
            <tr style="border-bottom:1px solid #233554;"><td style="padding:10px 5px;">🛡️ 安全性得分</td><td style="text-align:right; color:#64ffda; font-family:monospace; font-weight:bold;">{round(avg_s, 1)} / 10</td></tr>
            <tr style="border-bottom:1px solid #233554;"><td style="padding:10px 5px;">📈 獲利性得分</td><td style="text-align:right; color:#64ffda; font-family:monospace; font-weight:bold;">{round(avg_y, 1)} / 10</td></tr>
            <tr style="border-bottom:1px solid #233554;"><td style="padding:10px 5px;">☂️ 家庭保障度</td><td style="text-align:right; color:#64ffda; font-family:monospace; font-weight:bold;">{round(prot_sc, 1)} / 10</td></tr>
            <tr><td style="padding:10px 5px;">💧 變現流動性</td><td style="text-align:right; color:#64ffda; font-family:monospace; font-weight:bold;">{round(liq_sc, 1)} / 10</td></tr>
        </table>
        """, unsafe_allow_html=True)
        
    st.markdown(f"""
    <div class="advice-card">
        <h4 style="color:#64ffda; margin-top:0;">💡 CFP 專業精算結論</h4>
        <p style="font-size:14px; color:#e6f1ff; margin-bottom:0; line-height:1.6;">
            目標本金 <b style="color:#ffd166;">${st.session_state.target_goal:,}</b> 下每月領 <b style="color:#ffd166;">${st.session_state.expect_pension:,}</b> 可支領至 <b style="color:#ffd166;">{lon_text}</b>。<br>
            目前缺口 <b style="color:#ef476f;">${round(gap):,}</b>，建議每月儲存 <b style="color:#ef476f;">${round(monthly_save):,}</b>。
        </p>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.policies:
        st.markdown("<br><div style='font-weight:bold;font-size:16px;color:#64ffda;margin-bottom:10px;'>保單清單</div>", unsafe_allow_html=True)
        
        yR = max(0, st.session_state.retire_age - st.session_state.current_age)
        
        html_table = "<table style='width:100%; border-collapse:collapse; font-size:14px; color:#e6f1ff;'>"
        html_table += "<tr style='border-bottom:1px solid #233554; color:#8892b0; text-align:left;'>"
        html_table += "<th style='padding:10px 5px;'>保單號碼</th>"
        html_table += "<th style='padding:10px 5px;'>保單名稱</th>"
        html_table += f"<th style='padding:10px 5px; text-align:right;'>{st.session_state.retire_age}歲價值</th>"
        html_table += "</tr>"
        
        for p in st.session_state.policies:
            v = p['values']
            if yR <= 1: val_at_retire = v[0]
            elif yR <= 10: val_at_retire = v[0] + (v[1]-v[0])*((yR-1)/9)
            else:
                decade = math.floor(yR/10)
                idx1 = min(4, decade)
                idx2 = min(5, decade+1)
                val_at_retire = v[idx1] + (v[idx2]-v[idx1])*((yR%10)/10)
            
            v_retire = val_at_retire * (30 if p['currency'] == 'USD' else 1)
            
            p_no = str(p.get('policyNo', ''))
            if p_no.endswith('.0'): p_no = p_no[:-2]
            if p_no == '0': p_no = ''
            
            html_table += f"<tr style='border-bottom:1px solid #233554;'><td style='padding:10px 5px;'>{p_no}</td><td style='padding:10px 5px;'>{p['name']}</td><td style='padding:10px 5px; text-align:right; color:#64ffda; font-weight:bold; font-family:monospace;'>${v_retire:,.0f}</td></tr>"
            
        html_table += "</table><br>"
        st.markdown(html_table, unsafe_allow_html=True)

# ==========================================
# 8. 主畫面：AI 模擬器 (Simulation)
# ==========================================
elif st.session_state.current_view == 'simulation':
    st.markdown("<h2 style='text-align:center;color:#64ffda;margin-top:0;'>🤖 退休現金流壓力測試 V88.00</h2>", unsafe_allow_html=True)
    st.markdown("<div style='text-align:center;color:#8892b0;font-size:13px;margin-bottom:20px;'>三層式資金堆疊 | AI 最佳解建議 (20/80 Rule)</div>", unsafe_allow_html=True)
    
    baseIncome, counts, trajectories, optSafe, optRisk = run_monte_carlo()
    
    fig_mc = go.Figure()
    start_age = min(st.session_state.retire_age, 70)
    x_axis = list(range(start_age, 101))
    for i in range(min(50, len(trajectories))):
        fig_mc.add_trace(go.Scatter(x=x_axis, y=trajectories[i], mode='lines', 
                                    line=dict(width=1, color='rgba(100, 255, 218, 0.2)'), showlegend=False))
    fig_mc.update_layout(title=dict(text="自存金資產模擬走勢 (1000次迴圈)", font=dict(color='#8892b0', size=16)),
                         plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='#0a192f', font=dict(color='#8892b0'), 
                         height=450, margin=dict(l=0, r=0, t=40, b=0),
                         xaxis=dict(gridcolor='#233554'), yaxis=dict(gridcolor='#233554'))
    st.plotly_chart(fig_mc, use_container_width=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    c_stat1, c_stat2 = st.columns([1.5, 3])
    
    with c_stat1:
        st.markdown(f"""
        <div style="background:#172a45; padding:15px; border-radius:8px; border:1px solid #233554; text-align:center; height:100%;">
            <div style="font-size:14px; color:#8892b0;">勞保+勞退 (85歲前)</div>
            <div style="font-size:32px; font-weight:bold; color:#ffd166; margin:10px 0;">${baseIncome:,}</div>
            <div style="font-size:13px; color:#8892b0;">每月固定領</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c_stat2:
        st.markdown("""<div style="font-size:14px; color:#8892b0; margin-bottom:8px;">資產存續里程碑 (蒙地卡羅成功率)</div>""", unsafe_allow_html=True)
        rate_cols = st.columns(5)
        colors = ['#06d6a0', '#06d6a0', '#ffd166', '#ffd166', '#ef476f']
        ages = [80, 85, 90, 95, 100]
        for idx, age in enumerate(ages):
            rate = (counts[age] / 10)
            html = f"""
            <div style="background:rgba(255,255,255,0.05); border:1px solid {colors[idx]}; border-radius:6px; padding:15px 4px; text-align:center;">
                <div style="font-size:14px; color:{colors[idx]}; margin-bottom:4px;">{age} 歲</div>
                <div style="font-size:20px; font-weight:bold; color:{colors[idx]};">{rate:.1f}%</div>
            </div>
            """
            rate_cols[idx].markdown(html, unsafe_allow_html=True)
            
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div style='background:rgba(100,255,218,0.05); border:1px solid #64ffda; border-radius:8px; padding:20px;'>", unsafe_allow_html=True)
    st.markdown("<div style='font-weight:bold; color:#64ffda; font-size:16px; margin-bottom:15px;'>🤖 AI 現金流最佳解建議 (依據 80/20 Rule)</div>", unsafe_allow_html=True)
    
    ai_c1, ai_c2 = st.columns(2)
    with ai_c1:
        st.markdown(f"<span style='color:#06d6a0; font-size:16px;'>● 穩健提領 (80%勝率):</span> <span style='font-weight:bold; color:#fff; font-size:22px;'>${optSafe:,}</span> / 月", unsafe_allow_html=True)
        st.button("✅ 一鍵套用穩健建議", on_click=apply_ai_suggestion, args=(optSafe,), type="primary", use_container_width=True)
        
    with ai_c2:
        st.markdown(f"<span style='color:#ffd166; font-size:16px;'>● 積極提領 (50%勝率):</span> <span style='font-weight:bold; color:#fff; font-size:22px;'>${optRisk:,}</span> / 月", unsafe_allow_html=True)
        st.button("⚡ 一鍵套用積極建議", on_click=apply_ai_suggestion, args=(optRisk,), type="primary", use_container_width=True)
        
    st.markdown("</div>", unsafe_allow_html=True)

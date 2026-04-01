import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import ssl
import os
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

# 強化中文字型相容性 (同時支援 Mac/Windows/Linux)
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Microsoft JhengHei', 'PingFang HK', 'SimHei', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False
fmt = FuncFormatter(lambda x, p: f"{int(x):,}")

# =====================================================================
# 2. 網頁配置與標題
# =====================================================================
st.title("🏰 專業財顧視覺化戰略儀表板 (資產配置與傳承)")

# =====================================================================
# 3. 側邊欄參數 (加入 asset_ 前綴進行變數隔離)
# =====================================================================
st.sidebar.header("📁 客戶基礎資料")
uploaded_file = st.sidebar.file_uploader("上傳客戶資產檔案 (選填，若無則載入預設)", type=["xlsx"], key="asset_uploader")
annual_spend = st.sidebar.number_input("年度生活費目標 (萬元)", value=120, step=10, key="asset_annual_spend")
volatility = st.sidebar.slider("市場預期波動度 (%)", 1.0, 25.0, 10.0, key="asset_volatility") / 100
obs_years = st.sidebar.slider("規劃觀察年限 (年)", 10, 50, 35, key="asset_obs_years")
current_age = st.sidebar.number_input("客戶目前年齡", value=60, key="asset_current_age")
mdd_rate = st.sidebar.slider("極端市場跌幅測試 (%)", 10, 60, 30, key="asset_mdd_rate")

# =====================================================================
# 4. 數據清洗與載入
# =====================================================================
def load_and_clean_data(file):
    # 若有上傳檔案，優先讀取
    if file is not None:
        raw = pd.read_excel(file)
    else:
        # 若無上傳，則讀取 data 資料夾內的預設檔案
        default_path = os.path.join("data", "測試資產類型.xlsx")
        if os.path.exists(default_path):
            raw = pd.read_excel(default_path)
        else:
            # 最終備援方案：若連預設檔案都找不到，則套用寫死的數值
            raw = pd.DataFrame({
                "資產類別": ['股票型資產', '債券型基金', '年金給付(保險)', '租金收益(房產)', '現金與存款'],
                "金額": [15000000, 10000000, 10000000, 10000000, 5000000]
            })

    names = raw.iloc[:, 0].astype(str).tolist()
    # 金額自動轉換：大於100萬的自動除以10000換算成「萬元」
    vals = [v/10000 if v > 1000000 else v for v in pd.to_numeric(raw.iloc[:, 1], errors='coerce').fillna(0)]
    
    total = sum(vals)
    weights = {n: (v/total if total > 0 else 0) for n, v in zip(names, vals)}
    return names, vals, total, weights

c_names, c_vals, c_total, c_weights = load_and_clean_data(uploaded_file)

# --- 分類資產報酬設定 ---
st.sidebar.markdown("---")
st.sidebar.header("📈 個別資產預期報酬設定")
asset_returns = {}
for name in c_names:
    # 根據名稱簡單預判給予預設值
    if '股' in name or 'ETF' in name.upper(): d_r = 6.0
    elif '年金' in name or '保險' in name: d_r = 2.5
    elif '租金' in name or '房產' in name: d_r = 3.0
    elif '加密' in name: d_r = 10.0
    elif '債' in name: d_r = 4.0
    else: d_r = 1.5
    
    val = st.sidebar.number_input(f"{name} 報酬率(%)", value=d_r, step=0.5, key=f"asset_r_{name}")
    asset_returns[name] = val / 100

weighted_r = sum(c_weights[name] * asset_returns[name] for name in c_names)
st.sidebar.info(f"💡 組合加權報酬率: {weighted_r*100:.2f}%")
target_success = st.sidebar.slider("目標成功率門檻 (%)", 70, 100, 90, key="asset_target_success")

# =====================================================================
# 5. 核心引擎 (年初支出、年末複利)
# =====================================================================
def strategic_calculator(total, spend, rate, years, vol=0, iterations=1):
    all_results = []
    for _ in range(iterations):
        path = [total]; curr = total
        for _ in range(years):
            # 1. 確保年初先扣除生活費
            balance_after_spend = curr - spend
            # 2. 算複利 (僅針對剩餘部分)
            rand_r = np.random.normal(rate, vol) if vol > 0 else rate
            curr = balance_after_spend * (1 + rand_r) if balance_after_spend > 0 else 0
            path.append(max(0.0, float(curr)))
        all_results.append(path)
    return np.array(all_results)

# 全面同步運算
det_line = strategic_calculator(c_total, annual_spend, weighted_r, obs_years)[0]
mc_matrix = strategic_calculator(c_total, annual_spend, weighted_r, obs_years, vol=volatility, iterations=1000)
ages = np.arange(current_age, current_age + obs_years + 1)
actual_success = (np.sum(mc_matrix[:, -1] > 0) / 1000) * 100
med_line = np.median(mc_matrix, axis=0)

# =====================================================================
# 6. 視覺化展現
# =====================================================================

# ① 資產配置
st.subheader("① 資產配置比例")
fig1, ax1 = plt.subplots(figsize=(12, 6))
ax1.pie(c_vals, labels=[f"{n}\n({int(v):,}萬)" for n, v in zip(c_names, c_vals)], autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)
st.pyplot(fig1)

st.divider()

# ③ 壓力測試
st.subheader("③ 市場壓力測試：最大回撤模擬")
mdd_sim = [c_total]
for i in range(1, 13):
    change = -(mdd_rate/100) if i == 6 else np.random.normal(0, 0.015)
    mdd_sim.append(max(0.0, mdd_sim[-1] * (1 + change)))
fig2, ax2 = plt.subplots(figsize=(12, 5))
ax2.plot(range(13), mdd_sim, marker='o', color='#e74c3c', linewidth=2)
ax2.yaxis.set_major_formatter(fmt)
st.pyplot(fig2)
st.error(f"⚠️ 市場若發生 {mdd_rate}% 回撤，總資產將縮水至 {int(min(mdd_sim)):,} 萬。")

st.divider()

# ⑤ 退休金流 (對齊遞減邏輯)
st.subheader("⑤ 退休金流與資產消耗路徑 (定額版)")
fig3, ax3 = plt.subplots(figsize=(12, 5))
ax3.fill_between(ages, det_line, color='#3498db', alpha=0.15)
ax3.plot(ages, det_line, color='#3498db', linewidth=3)
ax3.yaxis.set_major_formatter(fmt)
ax_sec = ax3.twinx()
ax_sec.bar(ages, [annual_spend]*len(ages), color='#2ecc71', alpha=0.2)
st.pyplot(fig3)
st.info(f"💡 定額預估：資產預計支撐至 {ages[np.where(det_line <= 0)[0][0]] if any(det_line <= 0) else ages[-1]} 歲。")

st.divider()

# ⑦ 蒙地卡羅 (統一成功率標註)
st.subheader(f"⑦ 退休成功率模擬分析 (實測成功率: {actual_success:.1f}%)")
fig4, ax4 = plt.subplots(figsize=(12, 6))
for i in range(100):
    ax4.plot(ages, mc_matrix[i], color='#3498db' if mc_matrix[i][-1]>0 else '#e74c3c', alpha=0.05)
ax4.plot(ages, med_line, color='#2c3e50', linewidth=4, label='中位數路徑')
ax4.yaxis.set_major_formatter(fmt)
st.pyplot(fig4)
st.markdown(f"**💡 模擬結論：** 退休成功率為 **{actual_success:.1f}%**。中位數預估在 {ages[-1]} 歲時剩餘 **{int(med_line[-1]):,} 萬**。")

st.divider()

# ⑩ 傳承預估 (【修復重點】強制同步蒙地卡羅終點數據)
last_wealth = int(med_line[-1])
taxable = max(0, last_wealth - 1333) # 台灣現行遺產稅免稅額 1333 萬
tax = (taxable*0.1 if taxable<=5000 else (taxable*0.15-250 if taxable<=10000 else taxable*0.2-750))
inheritance = max(0, last_wealth - tax)

st.subheader(f"⑩ 資產傳承與稅務預估 (於 {ages[-1]}歲時)")
st.write(f"期末總資產：**{last_wealth:,} 萬** | 預計應納稅額：**{int(tax):,} 萬** | 子女淨繼承：**{int(inheritance):,} 萬**")
fig5, ax5 = plt.subplots(figsize=(12, 4))
bars = ax5.barh(['應納稅額', '子女淨繼承'], [tax, inheritance], color=['#e74c3c', '#2ecc71'])
ax5.xaxis.set_major_formatter(fmt)

# 顯示數值在長條圖上
for bar in bars:
    ax5.text(bar.get_width() + (last_wealth*0.01), bar.get_y() + bar.get_height()/2, 
             f'{int(bar.get_width()):,} 萬', va='center', ha='left', fontsize=12)

st.pyplot(fig5)

with st.expander("🔍 展開查看：各年齡資產餘額數據對帳表"):
    st.table(pd.DataFrame({
        "預估年齡": ages, 
        "中位數資產餘額 (萬)": med_line.astype(int)
    }))

# =====================================================================
# 7. 報告匯出功能
# =====================================================================
st.sidebar.markdown("---")
st.sidebar.header("📤 報告產出")

report_data = {
    "規劃參數": ["目前年齡", "觀察年限", "年度生活費", "組合加權報酬率", "市場波動度", "實測退休成功率"],
    "設定數值": [
        f"{current_age} 歲", 
        f"{obs_years} 年", 
        f"{annual_spend} 萬", 
        f"{weighted_r*100:.2f}%", 
        f"{volatility*100:.1f}%", 
        f"{actual_success:.1f}%"
    ]
}
report_df = pd.DataFrame(report_data)

csv = report_df.to_csv(index=False).encode('utf-8-sig')
st.sidebar.download_button(
    label="💾 下載戰略參數快照 (CSV)",
    data=csv,
    file_name=f'VIP_Retirement_Plan_{current_age}.csv',
    mime='text/csv',
    key="asset_download_btn"
)

if st.sidebar.button("🖨️ 產生列印預覽格式", key="asset_print_btn"):
    st.sidebar.write("### 💡 VIP 報告列印指引")
    st.sidebar.write("1. 請按下鍵盤 `Ctrl + P` (或 Mac 的 `Cmd + P`)。")
    st.sidebar.write("2. 目標印表機選擇 **「另存為 PDF」**。")
    st.sidebar.write("3. 佈局選擇 **「縱向」**，勾選 **「背景圖形」** 即可將所有圖表完整留存。")
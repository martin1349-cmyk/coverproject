
import streamlit as st
import pandas as pd

# ==========================================
# 0. 守門員：登入狀態檢查
# ==========================================
# 確保使用者是從 app.py 登入進來的
if not st.session_state.get("authenticated", False):
    st.warning("🔒 系統偵測到未授權的存取。請回到登入頁面進行身分驗證。")
    st.stop()  # 停止執行後續程式碼

# ==========================================
# 1. 應用程式主標題
# ==========================================
st.title("💼 CFP專用財務規劃工具：退休生活花費預估")
st.write("請點選下方頁籤切換不同的試算功能。")

# ==========================================
# 2. 建立五個頁籤與共用變數
# ==========================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 六都生活花費指數", 
    "🏥 晚年自費醫材預估", 
    "🏡 前十大養生村花費", 
    "📊 六都+醫材(月)", 
    "📊 養生村+醫材(月)"
])

# 共用變數：醫材目前總花費 (萬元)
total_med_current_10k = 15.0 + 22.9 + 38.4

# ==========================================
# 頁籤 1：六都生活花費指數
# ==========================================
with tab1:
    st.header("⚙️ 設定生活通膨變數")
    # 加入 age65_ 前綴進行 Session State 變數隔離
    years1 = st.slider("A: 計算通膨的年度 (年)", 1, 50, 10, 1, key="age65_tab1_years")
    rate1 = st.slider("B: 生活通膨的利率 (%)", 1.0, 10.0, 2.0, 0.1, key="age65_tab1_rate")

    bento_original_price = 100
    bento_future_price = bento_original_price * ((1 + rate1 / 100) ** years1)
    st.info(f"🍱 **特別說明：** 目前 **100 塊** 的便當，經過 {years1} 年後，將變成約 **{int(bento_future_price)} 塊**！")

    cities_data = {
        "台北市": 34014, "新北市": 25321, "桃園市": 26056,
        "台中市": 27333, "台南市": 21795, "高雄市": 23733
    }
    results1 = []
    for city, current_cost in cities_data.items():
        future_cost = current_cost * ((1 + rate1 / 100) ** years1)
        results1.append({
            "城市": city,
            "目前每月平均消費支出 (元)": current_cost,
            f"{years1} 年後預估生活費 (元)": int(future_cost)
        })
    st.header("📊 六都平均生活費變化表")
    st.dataframe(pd.DataFrame(results1), hide_index=True, use_container_width=True) # width="stretch" 在新版被 use_container_width 取代

# ==========================================
# 頁籤 2：晚年自費醫材預估
# ==========================================
with tab2:
    st.subheader("🅲 晚年必備重大自費醫材預估 (依目前市場主流均價)")
    st.write("⚙️ **設定醫療通膨變數**")
    years2 = st.slider("C: 距離需要使用醫材的年度 (年)", 1, 50, 20, 1, key="age65_tab2_years")
    rate2 = st.slider("D: 醫療通膨的利率 (%)", 1.0, 10.0, 3.0, 0.1, key="age65_tab2_rate")

    med_items = ["👁️ 視力重建 (雙眼)", "🫀 心血管防線 (支架2支+瓣膜1個)", "🦴 骨科與關節 (雙膝/雙髖+耗材)"]
    med_current_costs = [15.0, 22.9, 38.4]
    med_descriptions = ["特殊功能人工水晶體 (延伸焦距/三焦點)", "塗藥心臟血管支架、特殊材質生物心臟瓣膜", "特殊材質人工關節、導航/防沾黏耗材、疼痛管理"]
    
    med_future_costs = [round(cost * ((1 + rate2 / 100) ** years2), 1) for cost in med_current_costs]

    material_df = pd.DataFrame({
        "身體部位": med_items,
        "目前花費 (萬元)": med_current_costs,
        f"{years2} 年後預估花費 (萬元)": med_future_costs,
        "說明與主流選擇": med_descriptions
    })
    st.table(material_df)
    total_current = round(sum(med_current_costs), 1)
    total_future = round(sum(med_future_costs), 1)
    st.info(f"💡 **目前醫材總預算約 {total_current} 萬元**。經過 {years2} 年的醫療通膨後，預估將攀升至 **{total_future} 萬元**！\n\n建議透過高額『實支實付醫療險』即可有效轉嫁此品質費用。")
    st.markdown("---")

# ==========================================
# 頁籤 3：前十大養生村花費
# ==========================================
with tab3:
    st.subheader("🏡 前十大養生村花費一覽表")
    st.write("⚙️ **設定養生村通膨變數**")
    years3 = st.slider("E: 預計入住養生村的年度 (年)", 1, 50, 20, 1, key="age65_tab3_years")
    rate3 = st.slider("F: 養生村租金通膨利率 (%)", 1.0, 10.0, 2.0, 0.1, key="age65_tab3_rate")

    village_data = [
        {"類別": "頂級/都會型", "養生村名稱": "新光新板傑仕堡 (新北)", "目前起步月租 (萬元)": 8.8, "保證金與備註": "租期彈性，最高至8萬以上"},
        {"類別": "頂級/都會型", "養生村名稱": "亞洲健康智慧園區 (新竹)", "目前起步月租 (萬元)": 6.0, "保證金與備註": "保證金 600萬起"},
        {"類別": "頂級/都會型", "養生村名稱": "一里雲村醫養園區 (新竹)", "目前起步月租 (萬元)": 6.8, "保證金與備註": "保證金約 2個月租金"},
        {"類別": "頂級/都會型", "養生村名稱": "康寧生活會館 (台北)", "目前起步月租 (萬元)": 6.0, "保證金與備註": "主打飯店式服務"},
        {"類別": "中高端/生活型", "養生村名稱": "俊傑館全齡養生宅 (新北)", "目前起步月租 (萬元)": 4.5, "保證金與備註": "-"},
        {"類別": "中高端/生活型", "養生村名稱": "好好園館 (台中)", "目前起步月租 (萬元)": 5.1, "保證金與備註": "最高至 5.9萬"},
        {"類別": "中高端/生活型", "養生村名稱": "合勤共生宅 (台中)", "目前起步月租 (萬元)": 4.7, "保證金與備註": "保證金 7.6萬-15.6萬，租金最高至 8.7萬"},
        {"類別": "高CP值/大型機構", "養生村名稱": "長庚養生文化村 (桃園)", "目前起步月租 (萬元)": 2.75, "保證金與備註": "市場最熱門，最高至 3.5萬"},
        {"類別": "高CP值/大型機構", "養生村名稱": "潤福生活新象 (新北)", "目前起步月租 (萬元)": 1.7, "保證金與備註": "押金高 (約 750萬-1500萬) 但管理費較低"},
        {"類別": "高CP值/大型機構", "養生村名稱": "和順居老人住宿 (台南)", "目前起步月租 (萬元)": 1.85, "保證金與備註": "公辦民營，單人套房"}
    ]
    for village in village_data:
        future_rent = village["目前起步月租 (萬元)"] * ((1 + rate3 / 100) ** years3)
        village[f"{years3} 年後預估月租 (萬元)"] = round(future_rent, 2)

    cols = ["類別", "養生村名稱", "目前起步月租 (萬元)", f"{years3} 年後預估月租 (萬元)", "保證金與備註"]
    st.dataframe(pd.DataFrame(village_data)[cols], hide_index=True, use_container_width=True)
    st.caption("💡 註：養生村費用多依房型、健康狀況及所需服務而有所浮動，上表以公開資訊的『最低起步月租』作為通膨計算基準。")

# ==========================================
# 頁籤 4：六都生活花費 + 醫材花費 (月平均)
# ==========================================
with tab4:
    st.subheader("📊 六都生活花費 + 重大醫材攤提 (月現金流估算)")
    st.write("⚙️ **設定綜合變數**")
    
    col1, col2 = st.columns(2)
    with col1:
        years4 = st.slider("G: 預估年度 (年)", 1, 50, 20, 1, key="age65_tab4_years")
        rate4_life = st.slider("H: 生活通膨利率 (%)", 1.0, 10.0, 2.0, 0.1, key="age65_tab4_life_rate")
    with col2:
        amortize4 = st.slider("I: 預計退休餘命/攤提年數 (年)", 5, 40, 20, 1, key="age65_tab4_amortize")
        rate4_med = st.slider("J: 醫療通膨利率 (%)", 1.0, 10.0, 3.0, 0.1, key="age65_tab4_med_rate")

    # 1. 計算未來的總醫材費，並分攤至每個月 (換算為元)
    future_med_total = (total_med_current_10k * 10000) * ((1 + rate4_med / 100) ** years4)
    monthly_med_cost = future_med_total / (amortize4 * 12)

    # 2. 計算生活費並合併
    results4 = []
    for city, current_cost in cities_data.items(): # 沿用第一頁的六都資料
        future_life_cost = current_cost * ((1 + rate4_life / 100) ** years4)
        total_monthly = future_life_cost + monthly_med_cost
        
        results4.append({
            "城市": city,
            "預估生活費 (元/月)": int(future_life_cost),
            "重大醫材攤提 (元/月)": int(monthly_med_cost),
            "總計所需現金流 (元/月)": int(total_monthly)
        })

    st.dataframe(pd.DataFrame(results4), hide_index=True, use_container_width=True)
    st.info(f"💡 **算法說明**：將 {years4} 年後的醫材總花費（約 {round(future_med_total/10000, 1)} 萬元），平均攤提到 {amortize4} 年的退休生活（{amortize4 * 12} 個月）中，再加上未來的每月生活費，得出每月需準備的總現金流。")

# ==========================================
# 頁籤 5：養生村生活花費 + 醫材花費 (月平均)
# ==========================================
with tab5:
    st.subheader("📊 養生村租金 + 重大醫材攤提 (月現金流估算)")
    st.write("⚙️ **設定綜合變數**")
    
    col1, col2 = st.columns(2)
    with col1:
        years5 = st.slider("K: 預估年度 (年)", 1, 50, 20, 1, key="age65_tab5_years")
        rate5_rent = st.slider("L: 養生村租金通膨 (%)", 1.0, 10.0, 2.0, 0.1, key="age65_tab5_rent_rate")
    with col2:
        amortize5 = st.slider("M: 預計退休餘命/攤提年數 (年)", 5, 40, 20, 1, key="age65_tab5_amortize")
        rate5_med = st.slider("N: 醫療通膨利率 (%)", 1.0, 10.0, 3.0, 0.1, key="age65_tab5_med_rate")

    # 1. 計算未來的總醫材費，並分攤至每個月 (換算為元)
    future_med_total_5 = (total_med_current_10k * 10000) * ((1 + rate5_med / 100) ** years5)
    monthly_med_cost_5 = future_med_total_5 / (amortize5 * 12)

    # 2. 計算養生村租金並合併
    results5 = []
    for village in village_data: # 沿用第三頁的養生村資料
        current_rent_yuan = village["目前起步月租 (萬元)"] * 10000
        future_rent_yuan = current_rent_yuan * ((1 + rate5_rent / 100) ** years5)
        total_monthly_5 = future_rent_yuan + monthly_med_cost_5
        
        results5.append({
            "養生村名稱": village["養生村名稱"],
            "預估租金 (元/月)": int(future_rent_yuan),
            "重大醫材攤提 (元/月)": int(monthly_med_cost_5),
            "總計所需現金流 (元/月)": int(total_monthly_5)
        })

    st.dataframe(pd.DataFrame(results5), hide_index=True, use_container_width=True)
    st.info(f"💡 **算法說明**：將 {years5} 年後的醫材總花費平均攤提到 {amortize5} 年中，加上未來的每月養生村租金。需注意，多數養生村入住前尚需準備一筆數百萬元的「保證金」。")

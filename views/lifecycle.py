import streamlit as st
import pandas as pd
# 從根目錄匯入核心引擎
from core_engine import V88CoreEngine

# ==========================================
# 0. 守門員：登入狀態檢查
# ==========================================
if not st.session_state.get("authenticated", False):
    st.warning("🔒 系統偵測到未授權的存取。請回到登入頁面進行身分驗證。")
    st.stop()

# ==========================================
# 1. 初始化核心引擎 (快取避免重複載入)
# ==========================================
@st.cache_resource
def get_engine():
    engine = V88CoreEngine()
    if engine.load_life_table() and engine.clean_and_extract_data():
        engine.extend_life_table_to_110()
        return engine
    return None

engine = get_engine()

# ==========================================
# 2. 介面主體
# ==========================================
st.title("📊 餘命預估系統V1")
st.markdown("---")

if engine is None:
    st.error("❌ 系統引擎載入失敗，請確認 data 資料夾內有 113年全國web.xlsx")
    st.stop()

col1, col2 = st.columns([1, 2], gap="large")

with col1:
    st.header("📝 1. 客戶基本資料與風險評估")
    # 全部加上 key="lifecycle_..." 進行變數隔離
    client_name = st.text_input("客戶姓名", value="", placeholder="請輸入客戶姓名...", key="lifecycle_client_name")
    
    col_gender, col_age = st.columns(2)
    with col_gender:
        gender_tw = st.selectbox("性別", ["男性", "女性"], key="lifecycle_gender")
        gender_en = "Male" if gender_tw == "男性" else "Female"
    with col_age:
        current_age = st.number_input("目前年齡", min_value=20, max_value=85, value=50, key="lifecycle_age")
        
    st.markdown("### 🚬 2. 生活習慣與體態")
    col_smoke, col_h, col_w = st.columns([2, 1.2, 1.2])
    with col_smoke:
        is_smoking = st.checkbox("🚬 有抽菸習慣", value=False, key="lifecycle_smoking")
    with col_h:
        client_height = st.number_input("📏 身高(cm)", min_value=100.0, max_value=250.0, value=170.0, step=1.0, key="lifecycle_height")
    with col_w:
        client_weight = st.number_input("⚖️ 體重(kg)", min_value=30.0, max_value=200.0, value=65.0, step=1.0, key="lifecycle_weight")
    
    calc_bmi = client_weight / ((client_height / 100) ** 2)
    if calc_bmi >= 30: bmi_status = "🔴 肥胖 (高風險)"
    elif calc_bmi >= 25: bmi_status = "🟡 過重 (微風險)"
    elif calc_bmi < 18.5: bmi_status = "🟡 過輕 (微風險)"
    else: bmi_status = "🟢 正常區間"
    st.caption(f"💡 系統換算 BMI 值為：**{calc_bmi:.1f}** ({bmi_status})")
    
    st.markdown("### 🩸 3. 疾病風險樣態設定")
    chd_pct = st.slider("冠心病風險 (%)", 0, 100, 0, key="lifecycle_chd")
    stroke_pct = st.slider("腦中風風險 (%)", 0, 100, 0, key="lifecycle_stroke")
    diabetes_pct = st.slider("糖尿病風險 (%)", 0, 100, 0, key="lifecycle_diabetes")
    htn_pct = st.slider("高血壓風險 (%)", 0, 100, 0, key="lifecycle_htn_pct")
    mace_pct = st.slider("心血管不良事件 MACE (%)", 0, 100, 0, key="lifecycle_mace")
    is_htn = st.checkbox("⚠️ 已確診高血壓", value=False, key="lifecycle_is_htn")
    
    with st.expander("🧬 開啟進階設定：家族病史與精細運算 (選填)"):
        st.markdown("📝 **若客戶有直系血親癌症病史，系統將動態重算其危險勝算比 (Hazard Ratio) 與預期餘命。**")
        father_cancers = st.multiselect(
            "父親曾罹患之癌症", 
            ["無", "肺癌", "肝癌", "大腸直腸癌", "胃癌", "胰臟癌", "攝護腺癌"],
            default=["無"], key="lifecycle_father_cancers"
        )
        mother_cancers = st.multiselect(
            "母親曾罹患之癌症", 
            ["無", "肺癌", "肝癌", "大腸直腸癌", "胃癌", "胰臟癌", "乳癌", "子宮頸癌"],
            default=["無"], key="lifecycle_mother_cancers"
        )
    
    st.markdown("### 🦽 4. 長照財務缺口評估")
    col_ltc_cost, col_ltc_year = st.columns(2)
    with col_ltc_cost:
        ltc_monthly = st.slider("每月長照開銷(萬)", 3, 10, 5, key="lifecycle_ltc_monthly")
    with col_ltc_year:
        ltc_years = st.slider("預估長照年限(年)", 5, 15, 8, key="lifecycle_ltc_years")
    ltc_total_cost = ltc_monthly * 12 * ltc_years

    st.markdown("### 🏥 5. 醫療費用預估")
    eol_med_cost = st.slider("預估臨終重症醫療費 (萬)", 50, 500, 150, step=10, key="lifecycle_eol_cost")

    st.markdown("---")
    # 修正 width="stretch" 為 use_container_width=True
    calculate_btn = st.button("🚀 開始精算並回寫 Excel", use_container_width=True, type="primary", key="lifecycle_calc_btn")

with col2:
    st.header("📈 精算結果與回寫狀態")
    
    if calculate_btn:
        if not client_name.strip():
            st.warning("⚠️ 請先在左側填寫「客戶姓名」再進行精算！")
            st.stop() 
            
        client_info = {'name': client_name, 'gender': gender_en, 'age': current_age}
        health_factors = {
            'Smoking': is_smoking, 'Height': client_height, 'Weight': client_weight, 'BMI': calc_bmi,
            'CHD': chd_pct / 100.0, 'Stroke': stroke_pct / 100.0, 'Diabetes': diabetes_pct / 100.0, 
            'Hypertension_pct': htn_pct / 100.0, 'Hypertension': is_htn, 'MACE': mace_pct / 100.0,
            'LTC_Total_Cost': ltc_total_cost,
            'father_cancers': father_cancers,
            'mother_cancers': mother_cancers
        }
        
        with st.spinner("AI 核心引擎全火力運算中 (壽命/長照/醫療)..."):
            curve_A = engine.calculate_adjusted_survival_curve(gender=gender_en, current_age=current_age, health_factors=health_factors, medical_improvement=0.0, intervention_discount=0.0)
            curve_B = engine.calculate_adjusted_survival_curve(gender=gender_en, current_age=current_age, health_factors=health_factors, medical_improvement=0.04, intervention_discount=0.0)
            curve_C = engine.calculate_adjusted_survival_curve(gender=gender_en, current_age=current_age, health_factors=health_factors, medical_improvement=0.04, intervention_discount=0.30)
            
            if curve_B is not None:
                med_B = engine.calculate_expected_medical_cost(curve_B, health_factors, eol_med_cost, intervention_discount=0.0)
                med_C = engine.calculate_expected_medical_cost(curve_C, health_factors, eol_med_cost, intervention_discount=0.30)
                
                health_factors['Med_Total_Cost'] = round(med_B['expected_cum_med'].iloc[-1], 1)
                
                is_saved = engine.export_to_master_excel(client_info, health_factors, curve_B)
                if is_saved:
                    st.success(f"✅ 已完成精算！客戶 {client_name} 的資料已更新至資料庫。")
                
                # ==========================================
                # 區塊一：存活率分析
                # ==========================================
                st.markdown("---")
                st.subheader("🎯 存續里程碑 (活到該歲數的機率)")
                def draw_milestone_cards(title, curve_df):
                    st.markdown(f"**{title}**")
                    ages = [80, 85, 90, 95, 100]
                    colors = ["#38b09d", "#368a96", "#eeb451", "#d89650", "#c14f6b"] 
                    cols = st.columns(5)
                    for i, (col, age) in enumerate(zip(cols, ages)):
                        row = curve_df[curve_df['age'] == age]
                        prob = row['survival_probability'].values[0] * 100 if not row.empty else 0.0
                        html = f"""
                        <div style="border: 2px solid {colors[i]}; border-radius: 8px; padding: 12px 5px; text-align: center; margin-bottom: 15px;">
                            <div style="color: {colors[i]}; font-size: 1.0rem; font-weight: 600; margin-bottom: 5px;">{age} 歲</div>
                            <div style="color: {colors[i]}; font-size: 1.4rem; font-weight: 700;">{prob:.2f}%</div>
                        </div>"""
                        col.markdown(html, unsafe_allow_html=True)

                draw_milestone_cards("【A】傳統靜態生命表", curve_A)
                draw_milestone_cards("【B】AI 醫療推算 (未管理)", curve_B)
                draw_milestone_cards("【C】積極健康管理推算", curve_C)
                
                st.subheader("📉 終身存活率衰減曲線 (三軌比對)")
                survival_chart_data = pd.DataFrame({
                    '年齡': curve_A['age'], 
                    '【A】傳統靜態 (%)': (curve_A['survival_probability'] * 100).round(2),
                    '【B】未管理 (%)': (curve_B['survival_probability'] * 100).round(2),
                    '【C】積極管理 (%)': (curve_C['survival_probability'] * 100).round(2)
                }).set_index('年齡')
                st.line_chart(survival_chart_data, color=["#2B5B84", "#7BAFD4", "#D94F4F"])

                # ==========================================
                # 區塊二：長照與失能分析
                # ==========================================
                st.markdown("---")
                st.markdown("## 🦽 專屬長照與失能風險分析")
                st.error(f"**🚨 預估潛在長照總缺口：{ltc_total_cost} 萬元** *(每月 {ltc_monthly}萬 × 12月 × {ltc_years}年)*")
                st.subheader("📈 長照/失能發生機率對比 (壓縮失能期)")
                ltc_chart_data = pd.DataFrame({
                    '年齡': curve_B['age'], 
                    '【B】未管理長照機率 (%)': (curve_B['ltc_probability'] * 100).round(2),
                    '【C】積極管理長照機率 (%)': (curve_C['ltc_probability'] * 100).round(2),
                    '🚨 50% 警戒線 (%)': 50.0
                }).set_index('年齡')
                st.line_chart(ltc_chart_data, color=["#ff4b4b", "#38b09d", "#808080"])

                # ==========================================
                # 區塊三：醫療費用與 5% 機會成本精算
                # ==========================================
                st.markdown("---")
                st.markdown("## 🏥 終身醫療費用預測分析")
                st.info("💡 **【機會成本試算】** 醫療開銷不僅是直接支出的流失；若能透過健康管理省下每年的醫藥費，並投入市場假定獲取 **5% 年化報酬率**，將會產生驚人的財務差距！")
                
                rate = 0.05
                df_b = med_B[med_B['expected_annual_med'] > 0].copy()
                peak_b = df_b['age'].max() if not df_b.empty else current_age
                total_med_b = df_b['expected_annual_med'].sum()
                fv_b = sum(row['expected_annual_med'] * ((1 + rate) ** max(0, peak_b - row['age'])) for _, row in df_b.iterrows())
                opp_cost_b = fv_b - total_med_b
                
                df_c = med_C[med_C['expected_annual_med'] > 0].copy()
                peak_c = df_c['age'].max() if not df_c.empty else current_age
                total_med_c = df_c['expected_annual_med'].sum()
                fv_c = sum(row['expected_annual_med'] * ((1 + rate) ** max(0, peak_c - row['age'])) for _, row in df_c.iterrows())
                opp_cost_c = fv_c - total_med_c
                
                saved_total = fv_b - fv_c
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown(f'''
                    <div style="border: 2px solid #ff4b4b; background-color: #fff0f0; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                        <h3 style="color: #ff4b4b; margin-top: 0;">🔴 【B】未管理情境</h3>
                        <p style="font-size: 1.1rem; margin-bottom: 5px;">💸 實質醫療總花費：<b>{total_med_b:.1f} 萬</b></p>
                        <p style="font-size: 1.1rem; margin-bottom: 5px; color: #666;">📉 錯失的 5% 投資利息：<b>{opp_cost_b:.1f} 萬</b></p>
                        <hr style="border-color: #ffb3b3; margin: 10px 0;">
                        <h4 style="color: #ff4b4b; margin-bottom: 0;">🔥 總財務耗損：{fv_b:.1f} 萬</h4>
                    </div>
                    ''', unsafe_allow_html=True)
                    
                with col_m2:
                    st.markdown(f'''
                    <div style="border: 2px solid #38b09d; background-color: #f0fff8; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                        <h3 style="color: #38b09d; margin-top: 0;">🟢 【C】積極管理情境</h3>
                        <p style="font-size: 1.1rem; margin-bottom: 5px;">🛡️ 實質醫療總花費：<b>{total_med_c:.1f} 萬</b></p>
                        <p style="font-size: 1.1rem; margin-bottom: 5px; color: #666;">📉 錯失的 5% 投資利息：<b>{opp_cost_c:.1f} 萬</b></p>
                        <hr style="border-color: #a8e6cf; margin: 10px 0;">
                        <h4 style="color: #38b09d; margin-bottom: 0;">✅ 總財務耗損：{fv_c:.1f} 萬 <span style="font-size: 1rem; color: #d89650;">(為您守住 {saved_total:.1f} 萬)</span></h4>
                    </div>
                    ''', unsafe_allow_html=True)
                
                med_annual_data = pd.DataFrame({
                    '年齡': med_B['age'],
                    '【B】未管理 (年花費)': med_B['expected_annual_med'].round(1),
                    '【C】積極管理 (年花費)': med_C['expected_annual_med'].round(1)
                }).set_index('年齡')
                
                med_annual_data = med_annual_data[(med_annual_data['【B】未管理 (年花費)'] > 0) | (med_annual_data['【C】積極管理 (年花費)'] > 0)]
                st.bar_chart(med_annual_data, color=["#ff4b4b", "#38b09d"])

                # ==========================================
                # 區塊四：AI 最佳退休策略處方箋
                # ==========================================
                st.markdown("---")
                st.markdown(f"## 📋 AI 最佳退休策略處方箋：給 {client_name} 的專屬建議")
                
                advice_list = []
                
                if calc_bmi >= 25 or is_smoking:
                    advice_list.append(f"**🏃‍♂️ 生活型態重塑**：您目前的體態指標為「{bmi_status}」" + ("且有抽菸習慣" if is_smoking else "") + "。強烈建議啟動『積極健康管理』，這不僅能讓您有極高機率活過 85 歲，更能大幅延後高額醫療支出的發生年齡。")
                else:
                    advice_list.append(f"**🏃‍♂️ 保持優勢**：您目前的體態指標落在「{bmi_status}」，請繼續保持！健康的身體是您最棒的防禦資產。")
                
                if saved_total > 50:
                    advice_list.append(f"**🛡️ 醫療風險轉嫁**：透過健康管理，您可實質守住高達 **{saved_total:.1f} 萬元**（含機會成本）的財務耗損。建議及早檢視『實支實付醫療險』與『重大傷病險』額度，用小錢鎖定風險，把守下來的資金轉入 5% 穩健增值的理財工具中。")
                else:
                    advice_list.append(f"**🛡️ 醫療資金準備**：建議預留至少 {total_med_c:.1f} 萬元的醫療預備金，或透過『實支實付醫療險』來轉嫁未來必然發生的臨終醫療衝擊。")
                
                if htn_pct > 0 or stroke_pct > 0 or is_htn:
                    advice_list.append(f"**🦽 建立長照防火牆**：系統偵測到您有心血管/血壓相關風險，這將顯著提高晚年失能的機率。面對潛在 **{ltc_total_cost} 萬元** 的長照核彈，強烈建議提早提早規劃『長照險』或『失能險』，避免龐大照護費用拖垮家人的生活品質。")
                else:
                    advice_list.append(f"**🦽 長照財務信託**：未來潛在長照缺口達 **{ltc_total_cost} 萬元**，建議將部分退休金進行專款專用的信託規劃，或是配置能穩定產生現金流的收息資產來支付未來的長期月費。")

                st.markdown(f'''
                <div style="background-color: #f8f9fa; border-left: 5px solid #368a96; padding: 20px; border-radius: 0 8px 8px 0; font-size: 1.1rem; line-height: 1.8;">
                {'<br><br>'.join(advice_list)}
                </div>
                ''', unsafe_allow_html=True)
                
                st.info("💡 以上建議為 AI 系統依據精算模型產出之初稿，請與您的 CFP 國際認證高級理財規劃顧問進行深度討論，以量身訂做最適合您的專屬財務計畫。")

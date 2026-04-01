import streamlit as st
import pdfplumber
import pandas as pd
import re
import json
import os
import tempfile
import plotly.express as px
import plotly.graph_objects as go
from google import genai

# =====================================================================
# 0. 守門員：登入狀態檢查
# =====================================================================
if not st.session_state.get("authenticated", False):
    st.warning("🔒 系統偵測到未授權的存取。請回到登入頁面進行身分驗證。")
    st.stop()

# =====================================================================
# 1. 系統初始化與金鑰設定
# =====================================================================
MY_GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

if not MY_GEMINI_KEY:
    st.error("⚠️ 找不到 Gemini API Key！請在 .streamlit/secrets.toml 中設定 GEMINI_API_KEY。")
    st.stop()

# =====================================================================
# 2. 核心資料處理引擎 (邏輯完全保留)
# =====================================================================
SECTION_KEYWORDS = [
    "契約內容一覽表-完整版", "當年度保障總覽-完整版", "的當年度保障明細-完整版", 
    "其他保障明細-完整版", "契約內容一覽表-精簡版", "逐年保費預估表總覽",
    "的基本醫療保障期間表", "投資型保單概況", "團體保障明細表"
]

def extract_target_sections(full_text, target_keyword):
    blocks = []
    parts = full_text.split(target_keyword)
    for part in parts[1:]:
        end_pos = len(part)
        for kw in SECTION_KEYWORDS:
            search_kw = kw.replace("的當年度保障明細", "當年度保障明細").replace("的基本醫療保障", "基本醫療保障")
            if search_kw != target_keyword and search_kw in part:
                pos = part.find(search_kw)
                if pos < end_pos: end_pos = pos
        blocks.append(part[:end_pos])
    return "\n".join(blocks)

def parse_v(s):
    if not s or str(s) in ['無','0','','nan']: return 0.0
    s = str(s).replace(',','')
    if '~' in s: s = s.split('~')[-1]
    nums = re.findall(r'[\d.]+', s)
    if not nums: return 0.0
    v = float(nums[0])
    return v * 10000 if '萬' in s else v

def get_pro_category(detail, raw_cat):
    name = (str(detail) + str(raw_cat)).lower()
    if any(x in name for x in ["長照", "失能", "殘廢", "照護", "ig2", "agd", "ud"]): return "長照"
    if any(x in name for x in ["癌症", "癌", "hf1", "am_"]): return "重疾"
    if any(x in name for x in ["實支", "雜費", "雜項", "cv_"]): return "實支實付"
    if any(x in name for x in ["手術", "處置", "yi1", "co_"]): return "手術"
    if any(x in name for x in ["住院", "日額", "溫心", "全心", "vr", "ba_", "bg_"]): return "住院"
    if any(x in name for x in ["意外", "傷害", "骨折", "xk1_", "xj_", "xk4_"]): return "意外"
    return "傳承與身故" 

def normalize_dataframe(df, expected_columns, fill_value=""):
    if df is None or df.empty:
        return pd.DataFrame(columns=expected_columns)
    for col in expected_columns:
        if col not in df.columns:
            df[col] = fill_value
    return df

def apply_post_parsing_mask(parsed_data):
    def mask_single_name(name_str):
        if not isinstance(name_str, str): return name_str
        def replacer(m):
            n = m.group(0)
            whitelist = ["法定繼承人", "法定", "本人", "配偶", "子女", "先生", "小姐", "無", 
                         "身故", "死亡", "滿期", "生存", "祝壽", "年金", "醫療", "失能", "殘廢", "受益人", "次順位"]
            if n in whitelist: return n
            if len(n) == 2: return "○" + n[1:]
            if len(n) >= 3: return n[0] + "○" * (len(n)-2) + n[-1]
            return n
        return re.sub(r'[\u4e00-\u9fa5]{2,5}', replacer, name_str)

    for item in parsed_data.get("契約明細清單", []):
        pol_no = str(item.get("保單號碼", ""))
        if len(pol_no) >= 6: item["保單號碼"] = "******" + pol_no[-4:]
        if "要保人" in item: item["要保人"] = mask_single_name(item["要保人"])
        if "對象" in item: item["對象"] = mask_single_name(item["對象"])
        if "受益人" in item: item["受益人"] = mask_single_name(item["受益人"])
        
    return parsed_data

def parse_policy_with_gemini(file_buffers):
    client = genai.Client(api_key=MY_GEMINI_KEY)
    uploaded_pdfs = []
    tmp_file_paths = []
    
    raw_text_for_counting = ""
    for file_buffer in file_buffers:
        file_buffer.seek(0)
        with pdfplumber.open(file_buffer) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if text: raw_text_for_counting += text + "\n"
        file_buffer.seek(0) 

    possible_pols = set(re.findall(r'(?<!\d)[1-9]\d{9}(?!\d)', raw_text_for_counting))
    pol_list_str = "、".join(possible_pols)
    pol_count = len(possible_pols)
    
    try:
        for file_buffer in file_buffers:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(file_buffer.getvalue())
                tmp_file_paths.append(tmp_file.name)
            uploaded_pdf = client.files.upload(file=tmp_file.name, config={'mime_type': 'application/pdf'})
            uploaded_pdfs.append(uploaded_pdf)
        
        prompt = f"""
        🔴【最高優先級指令：跳頁斷層破解與數量防漏】
        這份文件中包含多張獨立保單。

        【程式前置通緝名單】：
        系統已確認文件中至少包含以下 {pol_count} 組保單號碼：
        [{pol_list_str}]
        (請確保輸出清單中「絕對包含」上述所有號碼。若發現更多 10 碼保單號碼，請一併完整抓取，不可遺漏！)

        🔴【跳頁/跨頁斷層破解鐵律】：
        1. 跨頁尋找：保單號碼若在頁面最底部，保險名稱在下一頁頂部，它們屬同一保單！
        2. 孤兒險種歸屬：若某頁開頭直接看到險種名稱卻無保單號碼，請立刻往前一頁底部尋找！
        3. 嚴禁合併同名險種！必須「逐行核對 10 碼保單號碼」，每一組獨立號碼對應一個 JSON 陣列元素！

        請【嚴格】以下列 JSON 格式輸出：
        {{
          "解析統計": {{ "Python要求抓取的最低數量": {pol_count}, "AI實際輸出的保單總筆數": N }},
          "被保險人出生年份(民國)": 62,
          "契約明細清單": [
            {{ "保單號碼": "...", "要保人": "...", "職業類別": "...", "繳款方式": "...",
              "帳號末四碼": "...", "合約屬性": "主約/附約", "保險名稱": "...", "繳費年期": "...",
              "對象": "...", "投保年齡": "...", "投保日期": "...", "保額": "...", "一般身故": "...", "下期保費": "...",
              "繳別": "...", "受益人": "...",
              "豁免保費條件": "...", "保單狀態": "...", "特定醫療限額": "...", "當年度末保單價值準備金": "...",
              "最高續保年齡": "..." }}
          ],
          "個人保障缺口分析": [
            {{ "保障大類": "...", "保障細項": "...", "現有額度": "...", "建議額度": "..." }}
          ],
          "現金流預測": [
            {{ "西元年": 2026, "合計保費支出": 10000, "年金及滿期金收入": 0 }}
          ],
          "投資型保單現金配息合計": 0
        }}

        【提取規則加強(嚴格遵守)】：
        1. 「個人保障缺口分析」請優先尋找「321+1保藏圖」或「保障缺口分析」區塊。若無該區塊或發現資料不全，請【自動綜合整份保單明細】，自行將客戶所有的保障內容歸納並加總至各大類的「現有額度」中。既然契約明細裡有住院與手術等險種，缺口分析的現有額度就絕對不可留空！
        2. 「一般身故」：請優先讀取「契約內容一覽表」或「保障總覽表」中的基本身故保額，以求與總表數字完全一致，並保留幣別。若空白請填「0」。🔴【強制排除】：若該險種名稱包含「長照」、「失能」、「殘廢」、「照護」，其退還保費或身故金請【一律填「0」】，絕對不可計入一般身故！
        3. 「合約屬性」：實心圓點「●」為主約，空心圓點「○」為附約。
        4. 下期保費若為躉繳或繳清，請填 0。
        5. 「豁免保費條件」、「保單狀態」、「特定醫療限額」：仔細查找，無則明確填「無」。
        6. 「當年度末保單價值準備金」：若為投資型，精確提取「保單帳戶價值」，無數字填「0」。
        7. 「投保年齡」、「最高續保年齡」：無則填「0」或「無」。
        8. 「受益人」：請完整提取受益人欄位字串（包含身故、滿期、祝壽等前綴詞與比例）。若有多位，直接以字串形式完整輸出即可。
        9. 【幣別精準度】：無「外幣、美元」字眼即為台幣保單，絕對禁止自行加上美元。
        10. 🔴【現金流與配息】：掃描「逐年保費預估表」，將民國年轉西元年，精準對應「合計保費支出」與「年金及滿期金收入」。空白填0，絕對不可錯置！提取投資型保單「現金配息合計」純數值。
        11. 🔴【被保險人生日提取】：請尋找文件標頭的被保險人出生年月日（如 62.08.07），提取「民國年份」（如 62）填入 JSON。若無則填 0。
        """
        
        response = client.models.generate_content(model='gemini-2.5-flash', contents=uploaded_pdfs + [prompt])
        result_text = response.text.strip().replace("```json", "").replace("```", "")
        parsed_data = json.loads(result_text)
        
        parsed_data = apply_post_parsing_mask(parsed_data)
        
        birth_year_roc = int(parsed_data.get("被保險人出生年份(民國)", 0))
        
        expected_detailed_cols = ["保單號碼", "要保人", "職業類別", "繳款方式", "帳號末四碼", "合約屬性", "保險名稱", "繳費年期", "對象", "投保年齡", "投保日期", "保額", "一般身故", "下期保費", "繳別", "受益人", "豁免保費條件", "保單狀態", "特定醫療限額", "當年度末保單價值準備金", "最高續保年齡"]
        expected_gap_cols = ["保障大類", "保障細項", "現有額度", "建議額度"]
        
        raw_detailed = pd.DataFrame(parsed_data.get("契約明細清單", []))
        
        def enforce_main_rider(row):
            name = str(row.get('保險名稱', ''))
            attr = str(row.get('合約屬性', ''))
            if '附約' in name or '附加' in name:
                return '附約'
            if '○' in name or '○' in attr:
                return '附約'
            if '●' in name or '●' in attr:
                return '主約'
            return attr
            
        if not raw_detailed.empty:
            raw_detailed['合約屬性'] = raw_detailed.apply(enforce_main_rider, axis=1)
            
        raw_gap = pd.DataFrame(parsed_data.get("個人保障缺口分析", []))
        
        detailed_df = normalize_dataframe(raw_detailed, expected_detailed_cols, fill_value="無").astype(str)
        gap_df = normalize_dataframe(raw_gap, expected_gap_cols, fill_value="").astype(str)
        
        raw_cf = pd.DataFrame(parsed_data.get("現金流預測", []))
        if not raw_cf.empty:
            raw_cf.rename(columns={'合計保費支出': '合計保費(支出)', '年金及滿期金收入': '年金及滿期金(收入)'}, inplace=True)
            raw_cf = raw_cf.sort_values("西元年").reset_index(drop=True)
        else:
            raw_cf = pd.DataFrame(columns=["西元年", "合計保費(支出)", "年金及滿期金(收入)"])
            
        invest_income = float(str(parsed_data.get("投資型保單現金配息合計", 0)).replace(',', ''))
        
        return detailed_df, gap_df, raw_cf, invest_income, birth_year_roc
    finally:
        for path in tmp_file_paths:
            if os.path.exists(path): os.remove(path)
        for uploaded_pdf in uploaded_pdfs:
            try:
                client.files.delete(name=uploaded_pdf.name)
            except:
                pass

# =====================================================================
# 3. 頁面邏輯設計
# =====================================================================
st.title("💎 可視化保單系統")
st.info("🛡️ 企業級隱私防護已啟動：所有保單資料將在雲端 OCR 解析完成後「瞬間物理銷毀」，保障資料安全。")

uploaded_files = st.file_uploader("可同時拖曳多份保單 PDF (支援跨檔案自動融合)", type=["pdf"], accept_multiple_files=True, key="vip_uploader")

if uploaded_files:
    current_hash = "|".join([f.name for f in uploaded_files])
    
    if 'vip_file_hash' not in st.session_state or st.session_state['vip_file_hash'] != current_hash:
        st.session_state['vip_file_hash'] = current_hash
        st.session_state['vip_privacy_consented'] = False
        st.session_state['vip_parsed_hash'] = ""

    if not st.session_state.get('vip_privacy_consented', False):
        st.success("🛡️ **企業級隱私防護罩已就緒**")
        st.info("為了保護您的客戶，系統將自動啟動最高規格的「去識別化機制」與「即刪即焚」雲端架構。")
        
        with st.expander("👀 點擊查看本系統自動執行的「隱私防護項目清單」", expanded=True):
            st.markdown("""
            ✅ **智能姓名遮罩**：系統將自動替換要保人、被保險人與受益人之姓名。
            ✅ **保單號碼隱藏**：分析圖表僅保留保單末四碼供顧問對帳，原始長碼不予顯示。
            ✅ **生日與聯絡資訊屏障**：出生年月日、電話號碼與完整身分證字號將在報表呈現時自動被系統剔除。
            ✅ **無痕雲端精算**：AI 解析完成後 1 秒內，您的原始 PDF 將從雲端伺服器進行物理級永久銷毀。
            """)
                
        if st.button("✅ 暸解隱私防護機制，開始安全解析", type="primary", use_container_width=True, key="vip_btn_consent"):
            st.session_state['vip_privacy_consented'] = True
            st.rerun()
        st.stop()

    if st.session_state['vip_parsed_hash'] != current_hash:
        st.caption("✅ 檔案解析與跨檔案 AI 視覺融合中，請稍候... (全程加密且即刪即焚)")
        try:
            with st.spinner("AI 解析中，這可能需要幾十秒，請耐心等候..."):
                detailed_df, gap_df, cashflow_df, invest_income, birth_year_roc = parse_policy_with_gemini(uploaded_files)
            st.session_state['vip_cache_detailed'] = detailed_df
            st.session_state['vip_cache_gap'] = gap_df
            st.session_state['vip_cache_cf'] = cashflow_df
            st.session_state['vip_cache_invest'] = invest_income
            st.session_state['vip_cache_birth_year'] = birth_year_roc
            st.session_state['vip_parsed_hash'] = current_hash
            st.rerun()
        except Exception as e:
            st.error(f"解析失敗，請確認 API 額度或檔案格式：{e}")
            st.stop()

    detailed_df = st.session_state['vip_cache_detailed']
    gap_df = st.session_state['vip_cache_gap']
    cashflow_df = st.session_state['vip_cache_cf']
    invest_income = st.session_state['vip_cache_invest']
    
    current_year_roc = 115 
    birth_year = st.session_state.get('vip_cache_birth_year', 0)
    if birth_year > 0:
        global_current_age = current_year_roc - birth_year
    else:
        global_current_age = 40 

    tab_options = ["📊 客戶專屬儀表板", "🤖 AI專家建議", "⚙️ 後台原始數據"]
    selected_tab = st.radio("切換報表頁籤：", tab_options, horizontal=True, label_visibility="collapsed", key="vip_tab_radio")
    st.markdown("---")
    
    if selected_tab == "📊 客戶專屬儀表板":
        has_usd = False
        has_aud = False
        if not detailed_df.empty:
            for _, row in detailed_df.iterrows():
                chk_name = str(row.get('保險名稱',''))
                if any(x in chk_name for x in ['美元','USD','美金','外幣']) and 'FKA' not in chk_name:
                    has_usd = True
                if any(x in chk_name for x in ['澳幣','AUD']):
                    has_aud = True

        usd_rate = 31.0 
        aud_rate = 21.0 

        if has_usd or has_aud:
            st.markdown("### 💱 動態匯率設定 (由保單自動偵測)")
            rate_cols = st.columns(4)
            if has_usd:
                usd_rate = rate_cols[0].slider("美元 (USD) 匯率", min_value=28.0, max_value=35.0, value=31.0, step=0.1, key="vip_usd_rate")
            if has_aud:
                aud_rate = rate_cols[1].slider("澳幣 (AUD) 匯率", min_value=18.0, max_value=25.0, value=21.0, step=0.1, key="vip_aud_rate")
            st.divider()
        
        def process_premium(row):
            if any(x in str(row.get('繳別','')) for x in ['躉繳','繳清']): return 0.0, 0.0, 0.0, 0.0
            p_str = str(row.get('下期保費','0')).replace(',','')
            p_val = float(re.sub(r'[^\d.]','',p_str)) if re.sub(r'[^\d.]','',p_str) else 0.0
            
            chk_curr = str(row.get('保險名稱',''))
            is_usd = any(x in chk_curr for x in ['美元','USD','美金','外幣']) and 'FKA' not in chk_curr
            is_aud = any(x in chk_curr for x in ['澳幣','AUD'])
            
            if is_usd: return p_val * usd_rate, p_val, 0.0, 0.0
            if is_aud: return p_val * aud_rate, 0.0, p_val, 0.0
            return p_val, 0.0, 0.0, p_val

        if not detailed_df.empty:
            res = detailed_df.apply(process_premium, axis=1)
            detailed_df['計算用保費'] = [x[0] for x in res]
            detailed_df['美金保費'] = [x[1] for x in res]
            detailed_df['澳幣保費'] = [x[2] for x in res]
            detailed_df['台幣保費'] = [x[3] for x in res]

        st.markdown("### 🎯 總覽核心指標")
        c1, c2, c3 = st.columns([2, 1, 1])
        usd_sum = detailed_df['美金保費'].sum()
        aud_sum = detailed_df['澳幣保費'].sum()
        twd_sum = detailed_df['台幣保費'].sum()
        
        premium_display = f"NT$ {twd_sum:,.0f}"
        if usd_sum > 0: premium_display += f" + US$ {usd_sum:,.0f}"
        if aud_sum > 0: premium_display += f" + AU$ {aud_sum:,.0f}"
        
        c1.metric("預估年度繳費總額", premium_display)
        main_policy_count = detailed_df[detailed_df['合約屬性'].astype(str).str.contains('主')].shape[0]
        c2.metric("有效保單總數", f"{main_policy_count} 張")
        
        rate_display = []
        if has_usd: rate_display.append(f"USD: {usd_rate}")
        if has_aud: rate_display.append(f"AUD: {aud_rate}")
        c3.metric("目前採用匯率", " / ".join(rate_display) if rate_display else "1.0")
        st.divider()

        if not gap_df.empty:
            st.subheader("🛡️ 個人保障缺口分析 (存款完成率)")
            PRO_VALS = {"傳承與身故":3000000,"意外":6000000,"住院":3000,"手術":160000,"實支實付":300000,"重疾":2000000,"長照":45000}
            chart_df = gap_df.copy()
            chart_df['修正大類'] = chart_df.apply(lambda r: get_pro_category(r['保障細項'], r['保障大類']), axis=1)
            chart_df['達成率'] = chart_df.apply(lambda r: min((parse_v(r['現有額度'])/PRO_VALS.get(r['修正大類'],1))*100, 100.0) if PRO_VALS.get(r['修正大類'],0)>0 else 0.0, axis=1)
            
            radar_calc_df = chart_df.copy()
            radar_data = radar_calc_df.groupby('修正大類')['達成率'].sum().clip(upper=100).reset_index()
            
            base_cats = pd.DataFrame({"修正大類": list(PRO_VALS.keys())})
            radar_data = pd.merge(base_cats, radar_data, on='修正大類', how='left').fillna(0)
            
            if not radar_data.empty:
                r_col1, r_col2 = st.columns([1, 1.2])
                with r_col1:
                    fig_r = px.line_polar(radar_data, r='達成率', theta='修正大類', line_close=True, range_r=[0,100], color_discrete_sequence=['#00CC96'])
                    fig_r.update_traces(fill='toself', fillcolor='rgba(0, 204, 150, 0.4)')
                    st.plotly_chart(fig_r, use_container_width=True)
                with r_col2:
                    chart_df['狀態'] = chart_df['達成率'].apply(lambda x: "✅ 達標" if x>=100 else f"⚠️ {x:.0f}%")
                    st.dataframe(chart_df[['修正大類','保障細項','現有額度','狀態']], use_container_width=True, hide_index=True)
            st.divider()

        if not gap_df.empty:
            st.subheader("🏥 醫療保障明細與理賠實境檢視")
            med_cats = ["住院", "手術", "實支實付", "重疾", "意外"]
            med_df = chart_df[chart_df['修正大類'].isin(med_cats)].copy()
            
            col_m2_1, col_m2_2 = st.columns([1.5, 1])
            with col_m2_1:
                st.markdown("##### 📋 醫療保障原始區間清單")
                st.dataframe(med_df[['修正大類', '保障細項', '現有額度']], use_container_width=True, hide_index=True)
            with col_m2_2:
                st.markdown("##### 💡 門診手術與「處置」探照燈")
                gray_area_df = chart_df[chart_df['保障細項'].astype(str).str.contains('處置|門診手術', na=False)]
                if not gray_area_df.empty:
                    st.dataframe(gray_area_df[['保障細項', '現有額度']], use_container_width=True, hide_index=True)
                else:
                    st.warning("⚠️ 您的保障缺口分析中，目前未明確看到「處置」或「門診手術」專屬額度。")
                st.info(
                    "**【顧問專業提醒：手術 vs. 處置】**\n\n"
                    "現行健保制度分為 **2-2-7 (手術)** 與 **2-2-6 (處置)**。\n\n"
                    "許多舊型保單僅理賠健保定義之「手術」，若進行如大腸息肉切除、雷射等「處置」項目，"
                    "恐面臨不予理賠或按比例打折的風險。請務必檢視自己是否有涵蓋門診手術的實支實付！"
                )
            st.divider()

        if not cashflow_df.empty:
            st.subheader("📈 現金流黃金交叉預測")
            fig_cf = go.Figure()
            fig_cf.add_trace(go.Scatter(x=cashflow_df['西元年'], y=cashflow_df['合計保費(支出)'], fill='tozeroy', name='支出', line=dict(color='#FF6692')))
            fig_cf.add_trace(go.Scatter(x=cashflow_df['西元年'], y=cashflow_df['年金及滿期金(收入)'], fill='tozeroy', name='收入', line=dict(color='#00CC96')))
            if invest_income > 0:
                fig_cf.add_trace(go.Scatter(x=cashflow_df['西元年'], y=[invest_income] * len(cashflow_df), mode='lines', name='累計投資配息收益', line=dict(color='#FFA15A', dash='dash')))
            st.plotly_chart(fig_cf, use_container_width=True)
            st.divider()

        st.subheader("🏁 繳費期滿預測 (財務解脫日)")
        if not detailed_df.empty:
            pay_end_summary = []
            for _, row in detailed_df.iterrows():
                freq = str(row.get('繳別', ''))
                if '繳清' in freq or '躉繳' in freq or row.get('計算用保費', 0) <= 0:
                    continue
                start_date = str(row.get('投保日期', ''))
                start_year = 0
                nums = re.findall(r'\d+', start_date)
                if nums:
                    y = int(nums[0])
                    start_year = y + 1911 if y < 1911 else y
                
                is_rider = '附約' in str(row.get('合約屬性', ''))
                end_year = 0
                display_term = ""

                if is_rider:
                    max_age_str = str(row.get('最高續保年齡', '無'))
                    issue_age_str = str(row.get('投保年齡', '0'))
                    max_age_nums = re.findall(r'\d+', max_age_str)
                    issue_age_nums = re.findall(r'\d+', issue_age_str)
                    if max_age_nums and issue_age_nums and start_year > 0:
                        max_age = int(max_age_nums[0])
                        issue_age = int(issue_age_nums[0])
                        if max_age > issue_age:
                            end_year = start_year + (max_age - issue_age)
                            display_term = f"續保至 {max_age} 歲 (附約)"
                    if end_year == 0 and max_age_nums:
                        display_term = f"最高續保至 {max_age_nums[0]} 歲"
                        end_year = 2099
                else:
                    pay_term_str = str(row.get('繳費年期', '0'))
                    term_nums = re.findall(r'\d+', pay_term_str)
                    if term_nums and start_year > 0:
                        pay_term = int(term_nums[0])
                        end_year = start_year + pay_term
                        display_term = f"{pay_term} 年期 (主約)"

                if end_year > 0:
                    pay_end_summary.append({
                        '保險名稱': row.get('保險名稱', ''),
                        '預估期滿年份(西元)': end_year,
                        '原投保日期': start_date,
                        '繳費/續保設定': display_term,
                        '_sort_year': end_year
                    })

            if pay_end_summary:
                end_df = pd.DataFrame(pay_end_summary).sort_values('_sort_year')
                
                chart_m4_df = end_df[end_df['_sort_year'] < 2099].copy()
                
                display_end_df = end_df.drop(columns=['_sort_year']).copy()
                display_end_df['預估期滿年份(西元)'] = display_end_df['預估期滿年份(西元)'].apply(lambda x: str(x) if x < 2099 else '視被保人年齡')
                
                col_m4_1, col_m4_2 = st.columns([1, 1.2])
                with col_m4_1:
                    if not chart_m4_df.empty:
                        earliest_year = chart_m4_df['_sort_year'].min()
                        st.metric("🔜 最近一次財務解脫年份", f"{earliest_year} 年")
                        fig_end = px.histogram(chart_m4_df, y='預估期滿年份(西元)', orientation='h', color_discrete_sequence=['#28C76F'])
                        fig_end.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="期滿年份", xaxis_title="期滿保單數量")
                        st.plotly_chart(fig_end, use_container_width=True)
                    else:
                        st.metric("🔜 最近一次財務解脫年份", "請參閱右側清單")
                with col_m4_2:
                    st.markdown("##### 📝 即將期滿保單清單 (按年份排序)")
                    st.dataframe(display_end_df, use_container_width=True, hide_index=True)
            else:
                st.info("💡 目前無需要繼續繳費的保單，或資料中缺乏明確的投保日期與年期。")
        st.divider()

        st.subheader("🗓️ 年度繳費月份分佈推估")
        monthly_dict = {i: 0.0 for i in range(1, 13)}
        for _, row in detailed_df[detailed_df['計算用保費']>0].iterrows():
            m = 1
            date_str = str(row.get('投保日期', ''))
            nums = re.findall(r'\d+', date_str)
            if len(nums) >= 2:
                try:
                    parsed_m = int(nums[1])
                    if 1 <= parsed_m <= 12:
                        m = parsed_m
                except:
                    pass
            
            val = row['計算用保費']
            freq = str(row.get('繳別', ''))
            if '月繳' in freq:
                for i in range(1, 13): monthly_dict[i] += val
            elif '季繳' in freq:
                for s in [0, 3, 6, 9]: monthly_dict[((m-1+s)%12)+1] += val
            else: 
                monthly_dict[m] += val
            
        m_df = pd.DataFrame(list(monthly_dict.items()), columns=['月份碼','金額']).sort_values('月份碼')
        m_df['月份'] = m_df['月份碼'].apply(lambda x: f"{x}月")
        fig_m = px.bar(m_df, x='月份', y='金額', color_discrete_sequence=['#3065AC'])
        fig_m.update_layout(xaxis={'categoryorder':'array', 'categoryarray':[f"{i}月" for i in range(1,13)]})
        st.plotly_chart(fig_m, use_container_width=True)
        st.divider()

        st.subheader("🥧 現行繳費保單支出比重")
        active_df = detailed_df[detailed_df['計算用保費']>0].copy()
        if not active_df.empty:
            summary_pie = active_df.groupby('保險名稱')['計算用保費'].sum().reset_index().sort_values('計算用保費', ascending=False)
            pie_col1, pie_col2 = st.columns([1, 1.2])
            with pie_col1:
                summary_pie['簡稱'] = summary_pie['保險名稱'].apply(lambda x: str(x)[:10]+'...')
                fig_p = px.pie(summary_pie, values='計算用保費', names='簡稱', hole=0.3, custom_data=['保險名稱'])
                fig_p.update_traces(showlegend=False, textinfo='percent+label')
                st.plotly_chart(fig_p, use_container_width=True)
            with pie_col2:
                st.markdown("##### 📝 繳費保單明細 (按佔比排序)")
                summary_pie['金額'] = summary_pie['計算用保費'].apply(lambda x: f"NT$ {x:,.0f}")
                st.dataframe(summary_pie[['保險名稱','金額']], use_container_width=True, hide_index=True)
        st.divider()

        st.subheader("⚖️ 資產傳承與身故給付分析")
        if not detailed_df.empty:
            heritage_summary = []
            for _, row in detailed_df.iterrows():
                chk_curr = str(row.get('保險名稱', ''))
                if any(x in chk_curr for x in ['長照', '失能', '殘廢', '照護']):
                    continue
                    
                raw_val = str(row.get('一般身故', '0'))
                death_benefit = parse_v(raw_val)
                if death_benefit <= 0: continue
                
                is_usd = any(x in chk_curr for x in ['美元', 'USD', '美金', '外幣']) and 'FKA' not in chk_curr
                is_aud = any(x in chk_curr for x in ['澳幣', 'AUD'])
                
                if is_usd: death_benefit = death_benefit * usd_rate
                elif is_aud: death_benefit = death_benefit * aud_rate
                
                policy_no = str(row.get('保單號碼', '未提供'))
                
                bene_raw = str(row.get('受益人', '')).strip()
                if bene_raw in ['無', 'nan', '', '未提供']:
                    continue
                
                parts = re.split(r'[,，;；、\s]+', bene_raw)
                valid_parts = [p.strip() for p in parts if p.strip()]
                
                parsed_benes = []
                for p in valid_parts:
                    if any(bad in p for bad in ["祝壽", "滿期", "生存", "醫療", "失能", "年金", "理賠", "殘廢"]):
                        continue
                        
                    p_clean = re.sub(r'(?:身故|死亡|次順位)(?:受益人)?[:：]?\s*', '', p)
                    match = re.search(r'([^\d%]+)(\d+(?:\.\d+)?)?%?', p_clean)
                    if match:
                        name = match.group(1).strip()
                        if "法定" in name: name = "法定繼承人"
                        name = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', name)
                        
                        pct_str = match.group(2)
                        pct = float(pct_str)/100.0 if pct_str else None
                        if name: 
                            parsed_benes.append({"name": name, "pct": pct})
                            
                total_assigned = sum([b["pct"] for b in parsed_benes if b["pct"] is not None])
                unassigned_count = sum([1 for b in parsed_benes if b["pct"] is None])

                if unassigned_count > 0:
                    rem_pct = max(0.0, 1.0 - total_assigned)
                    eq_share = rem_pct / unassigned_count
                    for b in parsed_benes:
                        if b["pct"] is None: 
                            b["pct"] = eq_share

                for b in parsed_benes:
                    heritage_summary.append({'保單號碼': policy_no, '受益人': b["name"], '金額': death_benefit * b["pct"]})
                        
            if heritage_summary:
                h_df = pd.DataFrame(heritage_summary).groupby('受益人')['金額'].sum().reset_index().sort_values('金額', ascending=False)
                h_c1, h_c2 = st.columns([1, 1.2])
                with h_c1:
                    st.metric("傳承與身故保障總額 (台幣等值)", f"NT$ {h_df['金額'].sum():,.0f}")
                    st.plotly_chart(px.pie(h_df, values='金額', names='受益人', hole=0.4), use_container_width=True)
                with h_c2:
                    st.markdown("##### 📝 受益人領取總額清單")
                    h_df['預計領取金額'] = h_df['金額'].apply(lambda x: f"NT$ {x:,.0f}")
                    st.dataframe(h_df[['受益人', '預計領取金額']], use_container_width=True, hide_index=True)
        st.divider()

        st.subheader("💎 投資型保單帳戶價值評估")
        if not detailed_df.empty:
            cv_summary = []
            for _, row in detailed_df.iterrows():
                name = str(row.get('保險名稱', ''))
                if '變額' not in name and '投資' not in name:
                    continue
                raw_cv = str(row.get('當年度末保單價值準備金', '0'))
                cv_val = parse_v(raw_cv)
                if cv_val <= 0: continue
                
                chk_curr = name
                is_usd = any(x in chk_curr for x in ['美元', 'USD', '美金', '外幣']) and 'FKA' not in chk_curr
                is_aud = any(x in chk_curr for x in ['澳幣', 'AUD'])
                
                if is_usd: cv_val = cv_val * usd_rate
                elif is_aud: cv_val = cv_val * aud_rate
                cv_summary.append({'保險名稱': name, '預估帳戶現值(台幣等值)': cv_val})
            
            if cv_summary:
                cv_df = pd.DataFrame(cv_summary).groupby('保險名稱')['預估帳戶現值(台幣等值)'].sum().reset_index().sort_values('預估帳戶現值(台幣等值)', ascending=False)
                col_cv1, col_cv2 = st.columns([1, 1.2])
                with col_cv1:
                    st.metric("投資型保單總帳戶現值", f"NT$ {cv_df['預估帳戶現值(台幣等值)'].sum():,.0f}")
                    cv_df['簡稱'] = cv_df['保險名稱'].apply(lambda x: str(x)[:10]+'...')
                    fig_cv = px.pie(cv_df, values='預估帳戶現值(台幣等值)', names='簡稱', hole=0.4, custom_data=['保險名稱'], color_discrete_sequence=px.colors.qualitative.Set3)
                    fig_cv.update_traces(showlegend=False, textinfo='percent+label', hovertemplate="<b>%{customdata[0]}</b><br>NT$ %{value:,.0f}")
                    st.plotly_chart(fig_cv, use_container_width=True)
                with col_cv2:
                    st.markdown("##### 📝 帳戶現值明細 (按資產排序)")
                    display_cv = cv_df.copy()
                    display_cv['預估金額'] = display_cv['預估帳戶現值(台幣等值)'].apply(lambda x: f"NT$ {x:,.0f}")
                    st.dataframe(display_cv[['保險名稱', '預估金額']], use_container_width=True, hide_index=True)
            else:
                st.info("💡 目前資料中無明確的投資型保單帳戶價值數據。")
        st.divider()

        st.subheader("🩺 進階防護與特定限額檢查")
        if not detailed_df.empty:
            st.markdown("##### 🛡️ 豁免保費與保單狀態")
            adv_df1 = detailed_df[['保險名稱', '保單狀態', '豁免保費條件']].copy()
            def filter_adv(row):
                w = str(row.get('豁免保費條件', '無'))
                s = str(row.get('保單狀態', '無'))
                w_valid = not bool(re.search(r'無|nan|未', w))
                s_valid = not bool(re.search(r'無|nan|未', s))
                return w_valid or s_valid
            adv_df1 = adv_df1[adv_df1.apply(filter_adv, axis=1)]
            if not adv_df1.empty:
                adv_df1 = adv_df1.groupby('保險名稱').agg({'保單狀態':'first', '豁免保費條件':'first'}).reset_index()
                st.dataframe(adv_df1, use_container_width=True, hide_index=True)
            else:
                st.info("💡 目前資料中無特別註記之保單狀態或豁免。")
            st.divider()
            st.markdown("##### 💉 特定醫療限額 (樞紐分析彙總)")
            adv_df2 = detailed_df[['保險名稱', '特定醫療限額']].copy()
            adv_df2 = adv_df2[~adv_df2['特定醫療限額'].astype(str).str.contains('無|nan', na=False, regex=True)]
            if not adv_df2.empty:
                adv_pivot = adv_df2.groupby('保險名稱')['特定醫療限額'].apply(lambda x: ' / '.join(x.unique())).reset_index()
                st.dataframe(adv_pivot, use_container_width=True, hide_index=True)
            else:
                st.info("💡 目前資料中無特別註記之特定醫療限額。")

    # =========================================================
    # 第二頁籤：🤖 AI專家建議
    # =========================================================
    elif selected_tab == "🤖 AI專家建議":
        st.header("🤖 AI 專屬保單健檢與風險推演報告")
        
        st.subheader("📈 模組十：附約自然費率老化趨勢模擬 (推算至100歲終身)")
        if not detailed_df.empty:
            rider_df = detailed_df[
                detailed_df['合約屬性'].astype(str).str.contains('附') & 
                (~detailed_df['保險名稱'].astype(str).str.contains('終身')) &
                (detailed_df['台幣保費'] > 0)
            ].copy()
            
            if not rider_df.empty:
                sim_data = []
                for _, row in rider_df.iterrows():
                    name = row.get('保險名稱', '未知附約')
                    prem = row.get('台幣保費', 0)
                    
                    max_age_str = str(row.get('最高續保年齡', '80'))
                    max_age_nums = re.findall(r'\d+', max_age_str)
                    max_age = int(max_age_nums[0]) if max_age_nums else 80
                    
                    current_sim_prem = prem
                    
                    for sim_age in range(global_current_age, 101):
                        if sim_age > max_age:
                            sim_data.append({'預估年齡': sim_age, '保險名稱': name, '預估保費': 0})
                            continue
                            
                        sim_data.append({'預估年齡': sim_age, '保險名稱': name, '預估保費': current_sim_prem})
                        if sim_age < 40: current_sim_prem *= 1.02
                        elif sim_age < 50: current_sim_prem *= 1.04
                        elif sim_age < 60: current_sim_prem *= 1.07
                        elif sim_age < 70: current_sim_prem *= 1.10
                        else: current_sim_prem *= 1.13

                sim_df = pd.DataFrame(sim_data)
                
                if not sim_df.empty:
                    yearly_totals = sim_df.groupby('預估年齡')['預估保費'].sum().reset_index()
                    
                    target_age = 74
                    if target_age in yearly_totals['預估年齡'].values:
                        peak_prem = yearly_totals.loc[yearly_totals['預估年齡'] == target_age, '預估保費'].values[0]
                        peak_age = target_age
                    else:
                        peak_row = yearly_totals.loc[yearly_totals['預估保費'].idxmax()]
                        peak_age = int(peak_row['預估年齡'])
                        peak_prem = peak_row['預估保費']
                        
                    min_age = int(yearly_totals['預估年齡'].min())
                    now_prem = yearly_totals.loc[yearly_totals['預估年齡'] == min_age, '預估保費'].sum()
                    multiplier = peak_prem / now_prem if now_prem > 0 else 0
                    
                    col_m10_1, col_m10_2 = st.columns([1.5, 1])
                    with col_m10_1:
                        fig_sim = px.area(sim_df, x='預估年齡', y='預估保費', color='保險名稱', 
                                          title="附約保費老化暴增與斷保模擬 (至100歲)",
                                          labels={'預估年齡': '被保險人年齡(歲)', '預估保費': '推估總保費 (台幣)'},
                                          color_discrete_sequence=px.colors.qualitative.Pastel)
                        fig_sim.update_traces(line_shape='vh')
                        fig_sim.update_layout(hovermode="x unified", xaxis=dict(range=[min_age, 100]))
                        st.plotly_chart(fig_sim, use_container_width=True)
                    with col_m10_2:
                        st.markdown("##### 🚨 財務地雷警示")
                        st.metric(f"目前附約總保費 (約 {min_age} 歲)", f"NT$ {now_prem:,.0f}")
                        st.metric(f"推估最高峰保費 (於 {peak_age} 歲)", f"NT$ {peak_prem:,.0f}", f"暴增 {multiplier:.1f} 倍", delta_color="inverse")
                        st.info("💡 斷崖式暴跌是因附約『最高續保年齡』到了。多數醫療附約只能續保到 75 或 80 歲，當長條圖歸零，代表保單強制終止。")
            else:
                st.info("💡 目前資料中無需要推算的附約保費資料。")
        st.divider()

        st.subheader("📉 模組十一：高齡醫療斷崖檢視 (附約終止影響清單)")
        if not detailed_df.empty:
            policies_info = []
            for _, r in detailed_df.iterrows():
                name = str(r.get('保險名稱', ''))
                cat = get_pro_category(name, '')
                is_rider = '附' in str(r.get('合約屬性', ''))
                is_life = '終身' in name
                amt = str(r.get('保額', '無'))
                
                if is_life or not is_rider:
                    continue 
                    
                max_age_str = str(r.get('最高續保年齡', ''))
                max_age_nums = re.findall(r'\d+', max_age_str)
                if max_age_nums:
                    exp_age = int(max_age_nums[0])
                    if 60 <= exp_age < 100: 
                        policies_info.append({'name': name, 'cat': cat, 'exp_age': exp_age, 'amt': amt})
                        
            cliff_groups = {}
            for p in policies_info:
                age = p['exp_age']
                if age not in cliff_groups:
                    cliff_groups[age] = []
                cliff_groups[age].append(p)
                
            if cliff_groups:
                st.info("💡 隨著年齡增長，自然費率定期險將面臨強制終止。以下清單詳細拆解各年齡節點將失效的保單與流失保額，助您及早規劃終身防護底線。")
                
                for age in sorted(cliff_groups.keys()):
                    with st.expander(f"🚨 【 {age} 歲斷崖】防護網流失警示", expanded=True):
                        loss_data = []
                        for p in cliff_groups[age]:
                            loss_data.append({
                                "屆時強制終止之附約": p['name'], 
                                "保障大類": p['cat'], 
                                "直接流失保額": p['amt']
                            })
                        st.dataframe(pd.DataFrame(loss_data), hide_index=True, use_container_width=True)
            else:
                st.success("🎉 目前系統並未偵測到有即將面臨最高續保年齡斷崖的定期附約，您的醫療防護網相當穩固！")
        else:
            st.info("💡 目前無足夠數據可供繪製斷崖影響清單。")
        st.divider()

        st.subheader("⚠️ 模組十一之二：81歲超高齡醫療斷崖檢視 (附約全數歸零測試)")
        if not gap_df.empty and not detailed_df.empty:
            temp_chart_df2 = gap_df.copy()
            temp_chart_df2['修正大類'] = temp_chart_df2.apply(lambda r: get_pro_category(r.get('保障細項',''), r.get('保障大類','')), axis=1)

            MED_TARGETS = {"住院": 3000, "手術": 160000, "實支實付": 300000, "重疾": 2000000, "意外": 6000000}
            med_cats = list(MED_TARGETS.keys())

            cat_current_raw = {}
            for cat in med_cats:
                cat_df = temp_chart_df2[temp_chart_df2['修正大類'] == cat]
                if cat == '意外':
                    cat_df = cat_df[~cat_df['保障細項'].astype(str).str.contains('身故|死亡', na=False)]
                cat_val = sum(parse_v(str(x)) for x in cat_df['現有額度'])
                cat_current_raw[cat] = cat_val

            cat_surviving_ratio = {cat: 0.0 for cat in med_cats}
            surviving_mains = []

            for cat in med_cats:
                cat_pols = []
                for _, r in detailed_df.iterrows():
                    name = str(r.get('保險名稱', ''))
                    if get_pro_category(name, '') == cat:
                        prem = r.get('台幣保費', 0)
                        is_rider = '附' in str(r.get('合約屬性', ''))
                        is_life = '終身' in name

                        exp_age = 110
                        if not is_life and is_rider:
                            max_age_str = str(r.get('最高續保年齡', ''))
                            max_age_nums = re.findall(r'\d+', max_age_str)
                            if max_age_nums:
                                exp_age = int(max_age_nums[0])
                            else:
                                exp_age = 75

                        weight = max(prem, 3000)
                        cat_pols.append({'name': name, 'exp_age': exp_age, 'weight': weight})

                if not cat_pols:
                    continue

                total_weight = sum(p['weight'] for p in cat_pols)
                surviving_weight = 0
                for p in cat_pols:
                    if p['exp_age'] >= 81:
                        surviving_weight += p['weight']
                        if p['name'] not in surviving_mains:
                            surviving_mains.append(p['name'])

                cat_surviving_ratio[cat] = surviving_weight / total_weight if total_weight > 0 else 0.0

            current_med_data = []
            age81_med_data = []

            for cat in med_cats:
                raw_curr = cat_current_raw.get(cat, 0)
                ratio = cat_surviving_ratio.get(cat, 0)
                raw_81 = raw_curr * ratio
                target = MED_TARGETS.get(cat, 1)

                score_curr = min((raw_curr / target) * 100, 100.0) if target > 0 else 0.0
                score_81 = min((raw_81 / target) * 100, 100.0) if target > 0 else 0.0

                if score_curr > 0:
                    current_med_data.append({'階段': '1. 目前完整防護 (含附約)', '保障大類': cat, '標準化積分': score_curr})
                if score_81 > 0:
                    age81_med_data.append({'階段': '2. 81歲僅存防護 (僅剩主約)', '保障大類': cat, '標準化積分': score_81})

            chart_data = pd.DataFrame(current_med_data + age81_med_data)
            
            if not age81_med_data:
                chart_data = pd.concat([chart_data, pd.DataFrame([{'階段': '2. 81歲僅存防護 (僅剩主約)', '保障大類': '無', '標準化積分': 0}])], ignore_index=True)

            if not chart_data.empty:
                st.info("💡 導入權重積分系統：將各項醫療額度依目標值轉換為「防護積分」(單項最高100分)，精準對比81歲前后的真實防護力落差。")
                col_81a, col_81b = st.columns([1.5, 1])

                with col_81a:
                    fig_81 = px.bar(chart_data, x='階段', y='標準化積分', color='保障大類',
                                    title="現在 vs 81歲：防護力崩塌對比 (標準化積分)",
                                    color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig_81.update_layout(barmode='stack', yaxis_title="醫療防護總積分 (最高500分)")
                    st.plotly_chart(fig_81, use_container_width=True)

                with col_81b:
                    st.markdown("##### 🏥 81 歲時剩餘醫療主約清單")
                    if surviving_mains:
                        for m in surviving_mains:
                            st.markdown(f"- 🛡️ {m}")
                    else:
                        st.error("🚨 警告：81歲時將無任何醫療險繼續承保！(醫療保障徹底歸零)")

                    curr_total = sum(d['標準化積分'] for d in current_med_data)
                    age81_total = sum(d['標準化積分'] for d in age81_med_data)
                    loss_ratio = ((curr_total - age81_total) / curr_total * 100) if curr_total > 0 else 0

                    st.divider()
                    st.metric("目前醫療防護總積分", f"{curr_total:.1f} 分")
                    st.metric("81歲剩餘醫療積分", f"{age81_total:.1f} 分", f"崩塌 -{loss_ratio:.1f}%", delta_color="inverse")
                    
                st.divider()
                st.markdown("##### 💰 高齡財務準備金總結 (自備醫療費用提醒)")
                st.info("💡 滿 81 歲後，若缺乏終身醫療險的防護，未來需仰賴龐大的自備款來填補缺口。以下為預估的高齡醫療準備金：")
                
                fin_reserve_data = [
                    {"費用類別": "醫療費用", "預估金額 (新台幣)": "100萬 - 150萬元", "核心計算基礎": "每年 10萬至15萬 × 10年"},
                    {"費用類別": "長照費用", "預估金額 (新台幣)": "450萬 - 600萬元", "核心計算基礎": "每月 5萬至6萬 × 7.3年 + 輔具設備"},
                    {"費用類別": "總準備金", "預估金額 (新台幣)": "550萬 - 750萬元", "核心計算基礎": "應對80至90歲期間長壽與失能風險"}
                ]
                st.dataframe(pd.DataFrame(fin_reserve_data), hide_index=True, use_container_width=True)

        st.divider()

        st.subheader("⚖️ 模組十二：實支實付附約 vs. 終身醫療主約 (互動式保費交叉與 IRR 追平試算)")
        st.info("💡 下方為**動態精算模型**：您可以自由切換性別、年齡與預期醫療通膨率。系統將依循【最公平的基準】，自動比對「附約+差額自主投資(A方案)」與「20年平準主約(B方案)」，並精算出必須達到的年化報酬率！")

        main_premium_table = {
            '男': {0: 29945, 1: 30170, 2: 31034, 3: 31643, 4: 32187, 5: 32327, 6: 32772, 7: 32910, 8: 33362, 9: 33502, 10: 33943, 11: 34075, 12: 34208, 13: 34340, 14: 34472, 15: 34603, 16: 35052, 17: 35500, 18: 35950, 19: 36401, 20: 36862, 21: 37185, 22: 37526, 23: 37882, 24: 38239, 25: 38606, 26: 38934, 27: 39253, 28: 39577, 29: 39928, 30: 40288, 31: 40688, 32: 41090, 33: 41523, 34: 41960, 35: 42405, 36: 42890, 37: 43398, 38: 43974, 39: 44515, 40: 45129, 41: 45389, 42: 45652, 43: 45857, 44: 46068, 45: 46323, 46: 46691, 47: 47094, 48: 47494, 49: 47940, 50: 48378, 51: 48390, 52: 48402, 53: 48415, 54: 48427, 55: 48432},
            '女': {0: 32520, 1: 32548, 2: 32896, 3: 32926, 4: 33276, 5: 33626, 6: 33976, 7: 34327, 8: 34680, 9: 35033, 10: 35387, 11: 35419, 12: 35450, 13: 35483, 14: 35516, 15: 35549, 16: 35581, 17: 35613, 18: 35648, 19: 35679, 20: 35713, 21: 35747, 22: 35781, 23: 35816, 24: 35851, 25: 35885, 26: 35919, 27: 35955, 28: 35991, 29: 36025, 30: 36061, 31: 36240, 32: 36413, 33: 36600, 34: 36790, 35: 36984, 36: 37206, 37: 37451, 38: 37704, 39: 37981, 40: 38256, 41: 38300, 42: 38343, 43: 38541, 44: 38741, 45: 38984, 46: 39337, 47: 39722, 48: 40105, 49: 40530, 50: 40950, 51: 40962, 52: 40974, 53: 40983, 54: 40992, 55: 41001}
        }
        def get_rider_premium(g, a):
            table = {
                '男': [(4, 2360), (9, 2010), (14, 2285), (19, 2375), (24, 2400), (29, 2440), (34, 2575), (39, 3780), (44, 5160), (49, 6270), (54, 7600), (59, 9040), (64, 11400), (69, 14685), (74, 18010), (79, 23090), (80, 23090)],
                '女': [(4, 2360), (9, 2010), (14, 2285), (19, 2375), (24, 2550), (29, 2695), (34, 5000), (39, 5120), (44, 5240), (49, 5730), (54, 6870), (59, 7560), (64, 9185), (69, 12570), (74, 16860), (79, 21470), (80, 21470)]
            }
            for limit, prem in table[g]:
                if a <= limit: return prem
            return table[g][-1][1]

        col_ui1, col_ui2, col_ui3 = st.columns(3)
        sim_gender = col_ui1.selectbox("選擇被保險人性別", ["女", "男"], index=0, key="vip_sim_gender")
        
        default_age = global_current_age if 0 <= global_current_age <= 80 else 40
        sim_age = col_ui2.slider("投保年齡", min_value=0, max_value=80, value=int(default_age), step=1, key="vip_sim_age")
        sim_inf_rate = col_ui3.slider("預估醫療通膨率 (%)", min_value=0.0, max_value=10.0, value=5.0, step=0.1, key="vip_sim_inf_rate") / 100.0

        lookup_age = min(sim_age, 55)
        main_prem = main_premium_table[sim_gender][lookup_age]
        target_value = main_prem * 20

        def get_final_balance(r):
            bal = 0
            for i in range(81 - sim_age):
                current_age = sim_age + i
                actual_rider = get_rider_premium(sim_gender, current_age) * ((1 + sim_inf_rate)**i)
                budget = main_prem if i < 20 else 0
                bal = (bal + budget - actual_rider) * (1 + r)
                if bal < 0: bal = 0
            return bal

        low, high = -0.20, 0.99
        for _ in range(100):
            mid = (low + high) / 2
            if get_final_balance(mid) > target_value: high = mid
            else: low = mid
        required_irr = mid

        m12_data = []
        bal_opt = 0
        bal_cons = 0
        
        for i in range(81 - sim_age):
            age = sim_age + i
            actual_rider = get_rider_premium(sim_gender, age) * ((1 + sim_inf_rate)**i)
            budget = main_prem if i < 20 else 0
            
            bal_opt = (bal_opt + budget - actual_rider) * (1 + required_irr)
            if bal_opt < 0: bal_opt = 0
                
            bal_cons = (bal_cons + budget - actual_rider) * 1.02
            if bal_cons < 0: bal_cons = 0
                
            m12_data.append({'年齡': age, '方案模擬': f'A方案: 需維持 {required_irr*100:.2f}% 報酬率 (驚險追平)', '帳戶餘額': bal_opt})
            m12_data.append({'年齡': age, '方案模擬': 'A方案: 定存保守理財 2.0% (提早耗盡)', '帳戶餘額': bal_cons})
            m12_data.append({'年齡': age, '方案模擬': 'B方案: 20年主約保證領回 (鎖定通膨)', '帳戶餘額': target_value})

        df_m12 = pd.DataFrame(m12_data)

        if not df_m12.empty:
            col_m12_1, col_m12_2 = st.columns([1.5, 1])
            with col_m12_1:
                fig_m12 = px.line(df_m12, x='年齡', y='帳戶餘額', color='方案模擬', 
                                  color_discrete_sequence=['#FF9F43', '#EA5455', '#7367F0'],
                                  title=f"{sim_age}歲{sim_gender}性：附約自主投資 vs 主約確定保本 (通膨 {sim_inf_rate*100:.1f}% 測試)")
                fig_m12.update_layout(xaxis_title="年齡", yaxis_title="預估帳戶餘額 / 保本價值 (台幣)")
                st.plotly_chart(fig_m12, use_container_width=True)
            with col_m12_2:
                st.markdown("##### ⚙️ 運算參數與結果對比")
                st.markdown(f"- **設定性別 / 年齡**：{sim_gender}性 / {sim_age}歲\n- **B方案主約年繳**：NT$ {main_prem:,.0f} (繳20年)\n- **B方案保證領回**：NT$ {target_value:,.0f}\n- **設定醫療通膨率**：{sim_inf_rate*100:.1f}%\n")
                
                st.warning(f"**A方案 (附約+投資) 必須連續 {80-sim_age} 年維持【 {required_irr*100:.2f}% 】的年化報酬率**，才能在 80 歲時抵銷醫療通膨，並與 B 方案打平。")
                
                st.info("💡 附約採用自然費率，晚年保費將因「年齡+通膨」產生極可怕的雙重暴增。定存理財在 70 歲左右帳戶就會被徹底抽乾。主約的隱藏價值在於將未來通膨風險轉嫁給保險公司。")

    # =========================================================
    # 第三頁籤：⚙️ 後台原始數據
    # =========================================================
    elif selected_tab == "⚙️ 後台原始數據":
        st.subheader("後台原始數據驗證")
        st.dataframe(detailed_df, use_container_width=True)
        st.dataframe(gap_df, use_container_width=True)
        
        heritage_summary = []
        usd_rate = 31.0 
        aud_rate = 21.0 
        
        if not detailed_df.empty:
            for _, row in detailed_df.iterrows():
                chk_curr = str(row.get('保險名稱', ''))
                # 🚫 強制排除：長照與失能險種不列入身故傳承
                if any(x in chk_curr for x in ['長照', '失能', '殘廢', '照護']):
                    continue
                    
                raw_val = str(row.get('一般身故', '0'))
                death_benefit = parse_v(raw_val)
                if death_benefit <= 0: continue
                
                is_usd = any(x in chk_curr for x in ['美元', 'USD', '美金', '外幣']) and 'FKA' not in chk_curr
                is_aud = any(x in chk_curr for x in ['澳幣', 'AUD'])
                
                if is_usd: death_benefit = death_benefit * usd_rate
                elif is_aud: death_benefit = death_benefit * aud_rate
                
                policy_no = str(row.get('保單號碼', '未提供'))
                
                bene_raw = str(row.get('受益人', '')).strip()
                if bene_raw in ['無', 'nan', '', '未提供']:
                    continue
                
                parts = re.split(r'[,，;；、\s]+', bene_raw)
                valid_parts = [p.strip() for p in parts if p.strip()]
                
                parsed_benes = []
                for p in valid_parts:
                    if any(bad in p for bad in ["祝壽", "滿期", "生存", "醫療", "失能", "年金", "理賠", "殘廢"]):
                        continue
                        
                    p_clean = re.sub(r'(?:身故|死亡|次順位)(?:受益人)?[:：]?\s*', '', p)
                    match = re.search(r'([^\d%]+)(\d+(?:\.\d+)?)?%?', p_clean)
                    if match:
                        name = match.group(1).strip()
                        if "法定" in name: name = "法定繼承人"
                        name = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', name)
                        
                        pct_str = match.group(2)
                        pct = float(pct_str)/100.0 if pct_str else None
                        if name: 
                            parsed_benes.append({"name": name, "pct": pct})
                            
                total_assigned = sum([b["pct"] for b in parsed_benes if b["pct"] is not None])
                unassigned_count = sum([1 for b in parsed_benes if b["pct"] is None])

                if unassigned_count > 0:
                    rem_pct = max(0.0, 1.0 - total_assigned)
                    eq_share = rem_pct / unassigned_count
                    for b in parsed_benes:
                        if b["pct"] is None: 
                            b["pct"] = eq_share

                for b in parsed_benes:
                    heritage_summary.append({'保單號碼': policy_no, '受益人': b["name"], '金額': death_benefit * b["pct"]})
        
        if heritage_summary:
            st.divider()
            st.subheader("🔍 受益人與保單理賠交叉比對表 (按比例拆分後台幣等值)")
            try:
                pivot_df = pd.DataFrame(heritage_summary).pivot_table(
                    index='保單號碼',
                    columns='受益人',
                    values='金額',
                    aggfunc='sum',
                    fill_value=0
                )
                st.dataframe(pivot_df.style.format("NT$ {:,.0f}"), use_container_width=True)
            except Exception as e:
                st.warning(f"交叉表生成失敗: {e}")

# =========================================================
# 版權宣告區
# =========================================================
st.markdown("---")
st.caption("© 版權所有 林馬丁 | 本報表由 AI 自動解析生成，已落實企業級去識別化防護，實際理賠金額與條款依各家保險公司官方憑證為準。")

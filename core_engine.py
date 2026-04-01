import pandas as pd
import numpy as np
import os
import math
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

class V88CoreEngine:
    def __init__(self, data_dir="data", output_dir="output"):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.life_table_path = os.path.join(self.data_dir, "113年全國web.xlsx")
        self.raw_data = None
        self.clean_life_tables = {'Male': None, 'Female': None}

    def load_life_table(self):
        try:
            self.raw_data = pd.read_excel(self.life_table_path, sheet_name=None)
            return True
        except Exception as e:
            return False

    def clean_and_extract_data(self):
        if self.raw_data is None or '表1' not in self.raw_data:
            return False
        df_raw = self.raw_data['表1']
        col_0 = df_raw.iloc[:, 0].astype(str).str.strip()
        male_idx = col_0[col_0 == '男性'].index
        female_idx = col_0[col_0 == '女性'].index
        if len(male_idx) == 0 or len(female_idx) == 0:
            return False
            
        male_start = male_idx[0]
        female_start = female_idx[0]
        
        df_male = df_raw.iloc[male_start:female_start].copy()
        df_female = df_raw.iloc[female_start:].copy()
        def process_block(df_block):
            df_clean = pd.DataFrame({
                'age': df_block.iloc[:, 0], 'qx': df_block.iloc[:, 1],
                'lx': df_block.iloc[:, 2], 'ex': df_block.iloc[:, 6]
            })
            df_clean = df_clean.dropna(subset=['age'])
            df_clean['age_str'] = df_clean['age'].astype(str).str.strip().str.replace('+', '', regex=False)
            df_clean = df_clean[df_clean['age_str'].str.isdigit()].copy()
            df_clean['age'] = df_clean['age_str'].astype(int)
            df_clean['qx'] = pd.to_numeric(df_clean['qx'], errors='coerce')
            df_clean['lx'] = pd.to_numeric(df_clean['lx'], errors='coerce')
            df_clean['ex'] = pd.to_numeric(df_clean['ex'], errors='coerce')
            return df_clean.drop(columns=['age_str']).reset_index(drop=True)
            
        self.clean_life_tables['Male'] = process_block(df_male)
        self.clean_life_tables['Female'] = process_block(df_female)
        return True

    def extend_life_table_to_110(self):
        for gender in ['Male', 'Female']:
            df = self.clean_life_tables[gender]
            if df is None or df.empty:
                continue
            max_age = int(df['age'].max())
            if max_age >= 110:
                continue
            df_filtered = df[df['age'] < max_age].copy()
            base_age = max_age - 1 
            base_qx = df_filtered.loc[df_filtered['age'] == base_age, 'qx'].values[0]
            new_rows = []
            current_qx = base_qx
            avg_growth_rate = 1.14 
            for age in range(max_age, 111):
                current_qx = min(current_qx * avg_growth_rate, 0.999) 
                new_rows.append({'age': age, 'qx': current_qx, 'lx': 0, 'ex': 0})
            df_extended = pd.concat([df_filtered, pd.DataFrame(new_rows)], ignore_index=True)
            self.clean_life_tables[gender] = df_extended
        return True

    def calculate_adjusted_survival_curve(self, gender, current_age, health_factors, medical_improvement=0.04, intervention_discount=0.0):
        if self.clean_life_tables[gender] is None:
            return None
        base_table = self.clean_life_tables[gender].copy()
        future_table = base_table[base_table['age'] >= current_age].copy()
        future_table = future_table.reset_index(drop=True)

        risk_multiplier = 1.0
        
        # 🟢 1. 基礎指標 (Checkbox與BMI) 保持原樣
        if health_factors.get('Hypertension', False): risk_multiplier *= 1.2 
        if health_factors.get('Smoking', False): risk_multiplier += 0.5  
        bmi = health_factors.get('BMI', 22.0)
        if bmi >= 30.0: risk_multiplier += 0.3  
        elif bmi >= 25.0: risk_multiplier += 0.1  
        elif bmi < 18.5: risk_multiplier += 0.15 

        # 🚀 2. 將「死板的開關」升級為「動態連動」：輸入20%與40%將有顯著差異！
        mace_val = health_factors.get('MACE', 0.0)
        if mace_val > 0: risk_multiplier *= (1.0 + mace_val) # MACE直接以百分比疊加倍數
        
        chd_val = health_factors.get('CHD', 0.0)
        if chd_val > 0: risk_multiplier += (chd_val * 0.5)   # 冠心病風險加入存活率計算
        
        stroke_val = health_factors.get('Stroke', 0.0)
        if stroke_val > 0: risk_multiplier += (stroke_val * 0.5) # 腦中風風險加入存活率計算
        
        diabetes_val = health_factors.get('Diabetes', 0.0)
        if diabetes_val > 0: risk_multiplier += (diabetes_val * 0.5) # 糖尿病風險加入存活率計算
        
        htn_pct_val = health_factors.get('Hypertension_pct', 0.0)
        if htn_pct_val > 0: risk_multiplier += (htn_pct_val * 0.3)

        # 🧬 3. 家族癌症病史外掛 (不影響主流程)
        father_cancers = health_factors.get('father_cancers', [])
        mother_cancers = health_factors.get('mother_cancers', [])
        cancer_hr = {
            "胰臟癌": 1.10, "肝癌": 1.06, "肺癌": 1.05, 
            "胃癌": 1.04, "大腸直腸癌": 1.04, "乳癌": 1.03, 
            "攝護腺癌": 1.02, "子宮頸癌": 1.02
        }
        cancer_risk_multiplier = 1.0
        for cancer in father_cancers:
            if cancer in cancer_hr: cancer_risk_multiplier *= cancer_hr[cancer]
        for cancer in mother_cancers:
            if cancer in cancer_hr: cancer_risk_multiplier *= cancer_hr[cancer]
                
        risk_multiplier *= cancer_risk_multiplier
        # ---------------------------------------------------------

        chronic_factor = max(0.0, risk_multiplier - 1.0)

        if risk_multiplier > 1.0 and intervention_discount > 0:
            excess_risk = risk_multiplier - 1.0
            risk_multiplier = 1.0 + (excess_risk * (1.0 - intervention_discount))

        years_passed = future_table['age'] - current_age
        taper_factor = (95 - future_table['age']) / (95 - 85)
        taper_factor = taper_factor.clip(lower=0.0, upper=1.0)
        dynamic_improvement = medical_improvement * taper_factor
        improvement_factor = (1 - dynamic_improvement) ** years_passed

        future_table['adjusted_qx'] = future_table['qx'] * risk_multiplier * improvement_factor
        future_table['adjusted_qx'] = future_table['adjusted_qx'].clip(upper=1.0)
        future_table['px'] = 1 - future_table['adjusted_qx']
        future_table['survival_probability'] = future_table['px'].cumprod()

        ltc_cumulative = 0.0
        ltc_probs = []
        for i, row in future_table.iterrows():
            age = row['age']
            base_ltc_transition = 0.0015 * (1.12 ** max(0, age - 50))
            chronic_transition = chronic_factor * 0.05
            total_transition = base_ltc_transition + chronic_transition
            total_transition *= (1.0 - medical_improvement)
            if intervention_discount > 0:
                total_transition *= (1.0 - intervention_discount)
            total_transition = min(total_transition, 0.4) 
            ltc_cumulative = ltc_cumulative + (1.0 - ltc_cumulative) * total_transition
            ltc_probs.append(ltc_cumulative)
            
        future_table['ltc_probability'] = ltc_probs
        return future_table[['age', 'qx', 'adjusted_qx', 'survival_probability', 'ltc_probability']]

    def calculate_expected_medical_cost(self, survival_curve, health_factors, eol_cost_wan=150.0, intervention_discount=0.0):
        # 醫療費用的運算保持原封不動
        med_excess = 0.0
        if health_factors.get('Hypertension', False): med_excess += 0.2 
        med_excess += health_factors.get('Diabetes', 0) * 0.5
        med_excess += health_factors.get('CHD', 0) * 0.5
        med_excess += health_factors.get('Stroke', 0) * 0.5
        if health_factors.get('Smoking', False): med_excess += 0.3
        
        if intervention_discount > 0:
            med_excess *= (1.0 - intervention_discount)
            
        med_multiplier = 1.0 + med_excess

        df = survival_curve.copy()
        
        raw_annual_costs = []
        prob_dying_list = []
        prev_surv = 1.0
        for i, row in df.iterrows():
            age = row['age']
            surv_prob = row['survival_probability']
            qx = row['adjusted_qx']
            
            prob_dying = prev_surv * qx
            prob_dying_list.append(prob_dying)

            if age < 65: base_cost = 2.0
            elif age < 75: base_cost = 4.0
            elif age < 85: base_cost = 7.0
            else: base_cost = 10.0

            alive_cost = base_cost * med_multiplier * surv_prob
            dying_cost = eol_cost_wan * prob_dying
            
            expected_annual = alive_cost + dying_cost
            raw_annual_costs.append(expected_annual)
            prev_surv = surv_prob

        df['raw_annual'] = raw_annual_costs
        df['prob_dying'] = prob_dying_list

        peak_age = df.loc[df['prob_dying'].idxmax(), 'age']

        annual_costs = []
        cumulative_costs = []
        cum_cost = 0.0

        for i, row in df.iterrows():
            age = row['age']
            raw_cost = row['raw_annual']

            if age <= peak_age:
                cost = raw_cost
            else:
                cost = 0.0 

            cum_cost += cost
            annual_costs.append(cost)
            cumulative_costs.append(cum_cost)

        df['expected_annual_med'] = annual_costs
        df['expected_cum_med'] = cumulative_costs
        return df[['age', 'expected_annual_med', 'expected_cum_med']]

    def export_to_master_excel(self, client_info, health_factors, survival_curve):
        target_ages = [80, 85, 90, 95, 100]
        life_probs = {}
        ltc_probs = {}
        for age in target_ages:
            row = survival_curve[survival_curve['age'] == age]
            if not row.empty:
                life_probs[f'life{age}'] = round(row['survival_probability'].values[0], 4)
                ltc_probs[f'ltc{age}'] = round(row['ltc_probability'].values[0], 4)
            else:
                life_probs[f'life{age}'] = None
                ltc_probs[f'ltc{age}'] = None
                
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "\\n" in creds_dict["private_key"]:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)

            sheet_id = "1ZIOdxoRwexIqFhYYNC8QXw2YSJYI6Yi9qZ6q8G34uyc"
            spreadsheet = client.open_by_key(sheet_id)

            cols = [
                '時間', '客戶姓名', '性別', '年齡', 
                '身高', '體重', 'BMI', '抽菸', 
                '冠心病', '腦中風', '糖尿病', '高血壓', '心血管不良事件',
                'life80', 'life85', 'life90', 'life95', 'life100',
                'ltc80', 'ltc85', 'ltc90', 
                '長照缺口(萬)', '終身醫療費(萬)'
            ]

            tab_name = "AI精算總表"
            ws_titles = [ws.title for ws in spreadsheet.worksheets()]
            
            if tab_name not in ws_titles:
                sheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=30)
                sheet.append_row(cols, value_input_option='USER_ENTERED')
                existing_data = [cols]
            else:
                sheet = spreadsheet.worksheet(tab_name)
                existing_data = sheet.get_all_values()
                if not existing_data:
                    sheet.append_row(cols, value_input_option='USER_ENTERED')
                    existing_data = [cols]

            client_name = str(client_info.get('name')).strip()
            current_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            
            new_record = {
                '時間': current_time, '客戶姓名': client_name,
                '性別': '男' if client_info.get('gender') == 'Male' else '女',
                '年齡': client_info.get('age', ''),
                '身高': health_factors.get('Height', 0), 
                '體重': health_factors.get('Weight', 0),
                'BMI': round(health_factors.get('BMI', 22.0), 1),
                '抽菸': '是' if health_factors.get('Smoking', False) else '否',
                '冠心病': health_factors.get('CHD', 0), 
                '腦中風': health_factors.get('Stroke', 0),
                '糖尿病': health_factors.get('Diabetes', 0), 
                '高血壓': health_factors.get('Hypertension_pct', 0),
                '心血管不良事件': health_factors.get('MACE', 0),
                '長照缺口(萬)': health_factors.get('LTC_Total_Cost', 0),
                '終身醫療費(萬)': health_factors.get('Med_Total_Cost', 0)
            }
            
            for age in target_ages:
                new_record[f'life{age}'] = life_probs.get(f'life{age}')
                if age <= 90: 
                    new_record[f'ltc{age}'] = ltc_probs.get(f'ltc{age}')

            row_data_strings = []
            for c in cols:
                val = new_record.get(c, "")
                if pd.isna(val) or val is None:
                    row_data_strings.append("")
                else:
                    if hasattr(val, 'item'): val = val.item()
                    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                        row_data_strings.append("")
                    else:
                        row_data_strings.append(str(val))

            found_idx = -1
            for i, row in enumerate(existing_data):
                if len(row) > 1 and str(row[1]).strip() == client_name:
                    found_idx = i + 1
                    break

            if found_idx != -1:
                end_col = chr(ord('A') + len(cols) - 1)
                sheet.update(
                    range_name=f'A{found_idx}:{end_col}{found_idx}', 
                    values=[row_data_strings],
                    value_input_option='USER_ENTERED'
                )
            else:
                sheet.append_row(row_data_strings, value_input_option='USER_ENTERED')

            return True
            
        except Exception as e:
            error_details = str(e)
            if hasattr(e, 'response'):
                try:
                    error_details += f" | 詳細原因：{e.response.text}"
                except:
                    pass
            st.error(f"⚠️ 寫入失敗！抓到的錯誤為：{error_details}")
            return False

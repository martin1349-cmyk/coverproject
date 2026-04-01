import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np 
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =====================================================================
# 0. 守門員：登入狀態檢查
# =====================================================================
if not st.session_state.get("authenticated", False):
    st.warning("🔒 系統偵測到未授權的存取。請回到登入頁面進行身分驗證。")
    st.stop()

# =====================================================================
# 1. 介面與參數設定
# =====================================================================
st.title("📈 投資組合複合報酬率 & 風險分析")

# --- 側邊欄參數設定 (全面加上 yahoostock_ 前綴隔離變數) ---
st.sidebar.header("1. 設定投資標的")
tickers_input = st.sidebar.text_input("輸入股票代碼 (逗號隔開)", value="1103.TW, 2317.TW, 2882.TW, 2330.TW", key="yahoostock_tickers")

st.sidebar.header("2. 回測設定")
years = st.sidebar.slider("回測年數", min_value=1, max_value=40, value=20, key="yahoostock_years")
monthly_investment = st.sidebar.number_input("每月定期定額金額 (元)", value=1000, step=500, key="yahoostock_monthly_inv")

dd_threshold = st.sidebar.slider("設定回撤深度警告線 (%)", min_value=10, max_value=70, value=30, step=1, key="yahoostock_dd")
rf_rate = st.sidebar.number_input("無風險利率設定 (%)", value=2.0, step=0.5, key="yahoostock_rf") / 100

# 解析並清理代碼
ticker_list = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]

# 權重分配
weights = []
if ticker_list:
    st.sidebar.subheader("3. 權重分配 (%)")
    for ticker in ticker_list:
        w = st.sidebar.number_input(f"{ticker} 權重", 0, 100, 100 // len(ticker_list), key=f"yahoostock_w_{ticker}")
        weights.append(w / 100)

# --- 圖表風格設定 ---
st.sidebar.subheader("4. 介面設定")
chart_theme = st.sidebar.selectbox(
    "選擇圖表顏色風格", 
    ["預設 (Streamlit)", "深色模式 (Plotly Dark)", "簡約白 (Simple White)", "專業灰 (Seaborn)"],
    key="yahoostock_theme"
)

theme_mapping = {
    "預設 (Streamlit)": None,
    "深色模式 (Plotly Dark)": "plotly_dark",
    "簡約白 (Simple White)": "simple_white",
    "專業灰 (Seaborn)": "seaborn"
}
selected_template = theme_mapping[chart_theme]

# --- 演算法進階設定 ---
st.sidebar.subheader("5. 演算法進階設定")
if len(ticker_list) > 0:
    min_allowed_weight = int(np.ceil(100 / len(ticker_list)))
else:
    min_allowed_weight = 100

default_max_weight = max(40, min_allowed_weight)

max_weight_limit_pct = st.sidebar.slider(
    "AI 模擬單一標的最高權重 (%)", 
    min_value=min_allowed_weight, 
    max_value=100, 
    value=default_max_weight, 
    step=5,
    help="限制 AI 尋找最佳組合時，不能重壓單一股票。當標的越少，此限制的下限會自動提高以防出錯。",
    key="yahoostock_max_weight"
)
max_weight_limit = max_weight_limit_pct / 100.0


# =====================================================================
# 2. 核心運算函數
# =====================================================================
@st.cache_data(ttl=3600)
def get_portfolio_analysis(tickers, period_years, weights, monthly_amt):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=period_years * 365)
    
    price_data = {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(start=start_date, end=end_date)
            if not hist.empty and 'Close' in hist.columns:
                price_data[t] = hist['Close']
        except Exception:
            pass
            
    if not price_data:
        return None, "找不到任何有效資料，請確認代碼是否完整且正確。"
        
    adj_close = pd.DataFrame(price_data)
    missing_tickers = [t for t in tickers if t not in adj_close.columns]
    if missing_tickers:
        return None, f"以下標的無法獲取資料：{', '.join(missing_tickers)}"

    adj_close = adj_close.dropna()
    if adj_close.empty:
        return None, "資料存在過多空值。請縮短回測年數或更換標的。"
    
    try:
        bm_hist = yf.Ticker('^TWII').history(start=start_date, end=end_date)
        if not bm_hist.empty and 'Close' in bm_hist.columns:
            bm_close = bm_hist['Close'].reindex(adj_close.index, method='ffill')
            bm_normalized = bm_close / bm_close.iloc[0]
        else:
            bm_normalized = None
    except Exception:
        bm_normalized = None
    
    normalized = adj_close / adj_close.iloc[0]
    portfolio_ls = (normalized * weights).sum(axis=1)
    
    daily_returns = portfolio_ls.pct_change().dropna()
    annual_volatility = daily_returns.std() * np.sqrt(252)
    
    roll_max_ptf = portfolio_ls.cummax()
    drawdown_ptf = portfolio_ls / roll_max_ptf - 1.0
    max_drawdown_ptf = drawdown_ptf.min()
    
    max_drawdown_bm = None
    if bm_normalized is not None:
        roll_max_bm = bm_normalized.cummax()
        drawdown_bm = bm_normalized / roll_max_bm - 1.0
        max_drawdown_bm = drawdown_bm.min()

    monthly_data = adj_close.resample('MS').first()
    shares_each_ticker = (monthly_amt * pd.Series(weights, index=tickers)) / monthly_data
    total_shares = shares_each_ticker.cumsum()
    portfolio_dca = (adj_close * total_shares.reindex(adj_close.index, method='ffill')).sum(axis=1)
    total_invested = monthly_amt * len(monthly_data)
    
    return {
        "ls_history": portfolio_ls,
        "dca_history": portfolio_dca,
        "drawdown_ptf": drawdown_ptf,
        "benchmark_history": bm_normalized,
        "max_drawdown_ptf": max_drawdown_ptf,
        "max_drawdown_bm": max_drawdown_bm,
        "annual_volatility": annual_volatility,
        "total_invested": total_invested,
        "final_value_dca": portfolio_dca.iloc[-1],
        "dates": adj_close.index,
        "actual_start_date": adj_close.index[0],
        "adj_close": adj_close 
    }, None

# =====================================================================
# 3. 執行與顯示
# =====================================================================
if not ticker_list:
    st.info("請在左側輸入股票代碼。")
elif abs(sum(weights) - 1.0) > 0.001: 
    st.warning("⚠️ 權重總和必須等於 100%，請調整左側設定。")
else:
    with st.spinner('正在計算報酬率與應用圖表風格...'):
        result, error_msg = get_portfolio_analysis(ticker_list, years, weights, monthly_investment)
    
    if error_msg:
        st.warning(f"⚠️ {error_msg}")
    else:
        actual_years = (result["dates"][-1] - result["dates"][0]).days / 365.25
        actual_years = max(actual_years, 1/365.25) 
        
        cagr = ((result["ls_history"].iloc[-1]) ** (1/actual_years) - 1) * 100
        dca_roi = ((result["final_value_dca"] / result["total_invested"]) - 1) * 100
        
        if result["annual_volatility"] > 0:
            sharpe_ratio = (cagr/100 - rf_rate) / result["annual_volatility"]
        else:
            sharpe_ratio = 0
        
        st.caption(f"💡 提示：目前實際計算的資料期間為 **{result['actual_start_date'].strftime('%Y-%m-%d')}** 至今。")

        # --- 數據儀表板 ---
        st.subheader("📊 績效指標")
        c1, c2, c3 = st.columns(3)
        c1.metric("投資組合 CAGR", f"{cagr:.2f}%")
        if result["benchmark_history"] is not None:
            bm_cagr = ((result["benchmark_history"].iloc[-1]) ** (1/actual_years) - 1) * 100
            c2.metric("大盤 CAGR (^TWII)", f"{bm_cagr:.2f}%")
        else:
            c2.metric("大盤 CAGR (^TWII)", "N/A")
            
        st.subheader("🛡️ 風險評估指標")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("最大回撤 (MDD)", f"{result['max_drawdown_ptf']*100:.2f}%")
        r2.metric("大盤 最大回撤", f"{result['max_drawdown_bm']*100:.2f}%" if result["benchmark_history"] is not None else "N/A")
        r3.metric("年化波動率", f"{result['annual_volatility']*100:.2f}%")
        r4.metric("夏普值 (Sharpe)", f"{sharpe_ratio:.2f}")

        st.subheader("💰 定期定額試算")
        c5, c6, c7 = st.columns(3)
        c5.metric("定期定額累積價值", f"${int(result['final_value_dca']):,}")
        c6.metric("定期定額總投入", f"${int(result['total_invested']):,}")
        c7.metric("定期定額總報酬", f"{dca_roi:.2f}%")

        # --- 繪圖區塊 ---
        st.subheader("📈 資產增長曲線")
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=result["dates"], y=result["ls_history"], name="你的投資組合", line=dict(color='#1f77b4', width=2.5)))
        if result["benchmark_history"] is not None:
            fig1.add_trace(go.Scatter(x=result["dates"], y=result["benchmark_history"], name="台股大盤 (^TWII)", line=dict(color='gray', width=2, dash='dash')))
        fig1.update_layout(template=selected_template, hovermode="x unified", xaxis_title="日期", yaxis_title="資產增長倍數", legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
        st.plotly_chart(fig1, use_container_width=True, theme=None if selected_template else "streamlit")

        st.subheader("📉 歷史回撤幅度 (Drawdown)")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=result["dates"], y=result["drawdown_ptf"] * 100, name="投資組合跌幅", fill='tozeroy', line=dict(color='red', width=1)))
        fig2.add_hline(y=-dd_threshold, line_dash="dash", line_color="orange", annotation_text=f"警戒線 -{dd_threshold}%", annotation_position="bottom right")
        fig2.update_layout(template=selected_template, hovermode="x unified", xaxis_title="日期", yaxis_title="下跌幅度 (%)", yaxis=dict(ticksuffix="%"))
        st.plotly_chart(fig2, use_container_width=True, theme=None if selected_template else "streamlit")

        # --- 進階分析區塊 ---
        if len(ticker_list) > 1:
            st.markdown("---")
            st.subheader("🗺️ 資產相關性與配置分析")
            
            col_heat, col_blank = st.columns([2, 1]) 
            with col_heat:
                st.write("**資產每日報酬率相關性 (Correlation Matrix)**")
                st.caption("數值越接近 1 代表漲跌越同步；越接近 0 則分散風險效果越好。")
                
                corr_matrix = result["adj_close"].pct_change().corr()
                
                fig_heat = go.Figure(data=go.Heatmap(
                    z=corr_matrix.values, x=corr_matrix.columns, y=corr_matrix.index,
                    text=np.round(corr_matrix.values, 2), texttemplate="%{text}", 
                    colorscale='RdBu_r', zmin=-1, zmax=1
                ))
                fig_heat.update_layout(template=selected_template, height=400)
                st.plotly_chart(fig_heat, use_container_width=True, theme=None if selected_template else "streamlit")

            with st.expander("🧮 AI 演算法建議：尋找最佳權重 (Markowitz 效率前緣)"):
                st.write(f"點擊下方按鈕，系統將透過 **蒙地卡羅模擬（產生 2,000 組隨機權重）** 找出最高夏普值組合。")
                st.write(f"🛡️ 目前啟動限制：單一標的最高不會超過 **{max_weight_limit_pct}%**。")
                
                if st.button("🚀 開始模擬最佳權重"):
                    with st.spinner("正在模擬限制權重下的 2,000 種投資組合，請稍候..."):
                        adj_close = result["adj_close"]
                        returns = adj_close.pct_change().dropna()
                        mean_returns = returns.mean() * 252
                        cov_matrix = returns.cov() * 252
                        
                        num_portfolios = 2000
                        sim_results = np.zeros((3, num_portfolios))
                        weights_record = []
                        np.random.seed(42)
                        
                        for i in range(num_portfolios):
                            w = np.random.random(len(ticker_list))
                            w /= np.sum(w) 
                            
                            while np.any(w > max_weight_limit):
                                excess = np.sum(w[w > max_weight_limit] - max_weight_limit)
                                w[w > max_weight_limit] = max_weight_limit
                                mask = w < max_weight_limit
                                if np.sum(mask) > 0:
                                    w[mask] += excess * (w[mask] / np.sum(w[mask]))
                                else:
                                    break 
                            
                            weights_record.append(w)
                            p_ret = np.sum(mean_returns * w)
                            p_std = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
                            
                            sim_results[0,i] = p_std 
                            sim_results[1,i] = p_ret 
                            sim_results[2,i] = (p_ret - rf_rate) / p_std if p_std > 0 else 0 
                        
                        max_sharpe_idx = np.argmax(sim_results[2])
                        best_w = weights_record[max_sharpe_idx]
                        max_sharpe_ret = sim_results[1, max_sharpe_idx]
                        max_sharpe_std = sim_results[0, max_sharpe_idx]
                        max_sharpe_ratio = sim_results[2, max_sharpe_idx]
                        
                        st.success(f"✅ 模擬完成！最高夏普值達到 **{max_sharpe_ratio:.2f}**，以下是演算法建議的最佳比例：")
                        
                        w_cols = st.columns(len(ticker_list))
                        for idx, col in enumerate(w_cols):
                            col.metric(f"{ticker_list[idx]} 建議權重", f"{best_w[idx]*100:.1f}%")
                        
                        fig3 = go.Figure()
                        fig3.add_trace(go.Scatter(
                            x=sim_results[0], y=sim_results[1], mode='markers', 
                            marker=dict(color=sim_results[2], colorscale='Viridis', showscale=True, size=5, colorbar=dict(title="夏普值")),
                            name="隨機模擬組合", hoverinfo="text",
                            text=[f"報酬率: {ret*100:.1f}%<br>風險: {std*100:.1f}%<br>夏普值: {sr:.2f}" for std, ret, sr in zip(sim_results[0], sim_results[1], sim_results[2])]
                        ))
                        fig3.add_trace(go.Scatter(
                            x=[max_sharpe_std], y=[max_sharpe_ret], mode='markers',
                            marker=dict(color='red', size=15, symbol='star', line=dict(width=2, color='DarkSlateGrey')),
                            name="最佳組合 (Max Sharpe)"
                        ))
                        best_weight_text = "<br>".join([f"{t}: {w*100:.1f}%" for t, w in zip(ticker_list, best_w)])
                        fig3.add_annotation(
                            x=max_sharpe_std, y=max_sharpe_ret, text=f"<b>⭐ 最佳配置</b><br>{best_weight_text}",
                            showarrow=True, arrowhead=1, ax=60, ay=-50,
                            bgcolor="rgba(255, 255, 255, 0.85)", font=dict(color="black", size=12), bordercolor="gray", borderwidth=1
                        )
                        fig3.update_layout(title=f"效率前緣散佈圖 (上限 {max_weight_limit_pct}% / 2,000 次模擬)", xaxis_title="年化波動率 (風險)", yaxis_title="年化報酬率", template=selected_template)
                        st.plotly_chart(fig3, use_container_width=True, theme=None if selected_template else "streamlit")

        # === 1. 預測未來走勢 ===
        st.markdown("---")
        st.subheader("🔮 策略擴充：未來走勢預測 (蒙地卡羅模擬)")
        with st.expander("點擊展開：基於歷史數據推演未來可能性 (幾何布朗運動)"):
            c_sim1, c_sim2 = st.columns(2)
            with c_sim1:
                sim_years = st.slider("預測未來年數", min_value=1, max_value=30, value=10, key="yahoostock_sim_years")
            with c_sim2:
                initial_capital = st.number_input("模擬初始投入資金 (元)", value=100000, step=10000, key="yahoostock_init_cap")

            if st.button("🎲 執行未來走勢模擬 (運算 1,000 次)"):
                with st.spinner(f"正在以矩陣運算推演未來 {sim_years} 年的 1,000 種宇宙走勢..."):
                    mu = cagr / 100
                    vol = result["annual_volatility"]
                    days = int(sim_years * 252)
                    sims = 1000
                    dt = 1/252
                    mu = min(mu, 0.5) 
                    np.random.seed(42) 
                    Z = np.random.normal(0, 1, (days, sims))
                    daily_drift = (mu - 0.5 * vol**2) * dt
                    daily_shock = vol * np.sqrt(dt) * Z
                    daily_returns_sim = np.exp(daily_drift + daily_shock)

                    price_paths = initial_capital * np.cumprod(daily_returns_sim, axis=0)
                    price_paths = np.vstack([np.ones(sims) * initial_capital, price_paths]) 

                    percentile_5 = np.percentile(price_paths, 5, axis=1)
                    percentile_50 = np.percentile(price_paths, 50, axis=1)
                    percentile_95 = np.percentile(price_paths, 95, axis=1)

                    fig_mc = go.Figure()
                    x_axis = np.arange(days + 1)
                    
                    random_indices = np.random.choice(sims, 50, replace=False)
                    for i in random_indices:
                        fig_mc.add_trace(go.Scatter(
                            x=x_axis, y=price_paths[:, i], mode='lines', 
                            line=dict(color='lightgray', width=0.5), showlegend=False, hoverinfo='skip'
                        ))

                    fig_mc.add_trace(go.Scatter(x=x_axis, y=percentile_95, name='前 5% 樂觀情境', mode='lines', line=dict(color='green', width=2, dash='dash')))
                    fig_mc.add_trace(go.Scatter(x=x_axis, y=percentile_50, name='50% 中位數 (最可能)', mode='lines', line=dict(color='blue', width=3)))
                    fig_mc.add_trace(go.Scatter(x=x_axis, y=percentile_5, name='後 5% 悲觀情境', mode='lines', line=dict(color='red', width=2, dash='dash')))

                    fig_mc.update_layout(
                        title=f"投入 {initial_capital:,} 元，未來 {sim_years} 年資產走勢預測",
                        xaxis_title="未來交易日", yaxis_title="預期資產價值 (元)",
                        template=selected_template, hovermode="x unified"
                    )
                    st.plotly_chart(fig_mc, use_container_width=True, theme=None if selected_template else "streamlit")

                    st.success(f"✅ 運算完成！若你將這個配置持續持有 {sim_years} 年，預估的資金變化如下：")
                    c_res1, c_res2, c_res3 = st.columns(3)
                    c_res1.metric("🔴 悲觀情境 (後5%)", f"${int(percentile_5[-1]):,}")
                    c_res2.metric("🔵 最可能情境 (中位數)", f"${int(percentile_50[-1]):,}")
                    c_res3.metric("🟢 樂觀情境 (前5%)", f"${int(percentile_95[-1]):,}")

        # === 2. 策略升級：定期再平衡 ===
        st.markdown("---")
        st.subheader("⚖️ 策略擴充：定期再平衡 (Rebalancing)")
        with st.expander("點擊展開：比較「買進持有」與「每年底定期再平衡」的績效差異"):
            if len(ticker_list) > 1:
                st.write("👉 定期再平衡會強迫你在每年底「賣出漲多的、買進跌深的」，強制讓投資組合回到你左側設定的初始權重比例。")
                if st.button("🔄 執行再平衡回測"):
                    with st.spinner("正在逐年計算年底的權重重置..."):
                        adj_close = result["adj_close"].copy()
                        year_end_dates = adj_close.resample('YE').last().index 
                        
                        rebalance_history = []
                        current_capital = 1.0 
                        
                        for i in range(len(year_end_dates)):
                            end_date = year_end_dates[i]
                            if i == 0:
                                year_data = adj_close.loc[:end_date]
                            else:
                                prev_end_date = year_end_dates[i-1]
                                year_data = adj_close.loc[prev_end_date:end_date]
                                
                            if len(year_data) <= 1:
                                continue
                                
                            year_normalized = year_data / year_data.iloc[0]
                            year_portfolio = (year_normalized * weights).sum(axis=1) * current_capital
                            
                            if i > 0:
                                year_portfolio = year_portfolio.iloc[1:]
                                
                            rebalance_history.append(year_portfolio)
                            current_capital = year_portfolio.iloc[-1]
                            
                        rebalanced_series = pd.concat(rebalance_history)
                        reb_actual_years = (rebalanced_series.index[-1] - rebalanced_series.index[0]).days / 365.25
                        reb_cagr = ((rebalanced_series.iloc[-1]) ** (1/reb_actual_years) - 1) * 100
                        reb_roll_max = rebalanced_series.cummax()
                        reb_drawdown = rebalanced_series / reb_roll_max - 1.0
                        reb_mdd = reb_drawdown.min() * 100
                        
                        bh_series = result["ls_history"]
                        bh_cagr = cagr
                        bh_mdd = result['max_drawdown_ptf'] * 100
                        
                        st.success("✅ 再平衡回測完成！下方綠色或紅色的數值，代表「再平衡」相比「買進持有」的差異：")
                        c_reb1, c_reb2, c_reb3 = st.columns(3)
                        diff_cagr = reb_cagr - bh_cagr
                        c_reb1.metric("每年再平衡 CAGR", f"{reb_cagr:.2f}%", f"{diff_cagr:.2f}% vs 買進持有")
                        
                        diff_mdd = reb_mdd - bh_mdd
                        mdd_color = "normal" if diff_mdd > 0 else "inverse" 
                        c_reb2.metric("每年再平衡 最大回撤", f"{reb_mdd:.2f}%", f"{diff_mdd:.2f}% vs 買進持有", delta_color=mdd_color)
                        c_reb3.metric("再平衡 最終資產倍數", f"{rebalanced_series.iloc[-1]:.2f}x", f"{rebalanced_series.iloc[-1] - bh_series.iloc[-1]:.2f}x vs 買進持有")

                        fig_reb = go.Figure()
                        fig_reb.add_trace(go.Scatter(x=rebalanced_series.index, y=rebalanced_series, name="每年定期再平衡", line=dict(color='orange', width=2.5)))
                        fig_reb.add_trace(go.Scatter(x=bh_series.index, y=bh_series, name="買進持有 (不做任何處理)", line=dict(color='#1f77b4', width=2, dash='dot')))
                        fig_reb.update_layout(title="策略比較：買進持有 vs 每年再平衡 (起點基準=1)", xaxis_title="日期", yaxis_title="資產增長倍數", template=selected_template, hovermode="x unified", legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
                        st.plotly_chart(fig_reb, use_container_width=True, theme=None if selected_template else "streamlit")
            else:
                st.info("⚠️ 定期再平衡需要至少 2 檔以上的標的才能進行喔！請在左側新增標的。")

        # === 3. 穩定度檢驗：滾動報酬率 ===
        st.markdown("---")
        st.subheader("⏱️ 策略擴充：穩定度檢驗 (滾動報酬率)")
        with st.expander("點擊展開：檢驗「無論何時進場，只要抱滿 N 年」的勝率與平均績效"):
            roll_years = st.slider("設定持有年數 (滾動視窗)", min_value=1, max_value=10, value=3, key="yahoostock_roll_years")
            if st.button(f"📊 計算持有 {roll_years} 年滾動報酬"):
                with st.spinner("正在計算歷史所有可能進場點的報酬率..."):
                    portfolio_series = result["ls_history"]
                    window_days = int(roll_years * 252)
                    
                    if len(portfolio_series) <= window_days:
                        st.warning(f"⚠️ 歷史資料長度不足！無法計算持有 {roll_years} 年的滾動報酬。請在左側增加「回測年數」或縮短這裡的持有年數。")
                    else:
                        rolling_cagr = (portfolio_series / portfolio_series.shift(window_days)) ** (1 / roll_years) - 1.0
                        rolling_cagr = rolling_cagr.dropna() * 100 
                        
                        win_rate = (rolling_cagr > 0).mean() * 100
                        avg_roll_cagr = rolling_cagr.mean()
                        max_roll_cagr = rolling_cagr.max()
                        min_roll_cagr = rolling_cagr.min()
                        
                        st.success(f"✅ 計算完成！以下是過去歷史中，**任何一天進場並死抱 {roll_years} 年**的真實數據：")
                        c_roll1, c_roll2, c_roll3, c_roll4 = st.columns(4)
                        c_roll1.metric("正報酬機率 (勝率)", f"{win_rate:.1f}%")
                        c_roll2.metric("平均年化報酬率", f"{avg_roll_cagr:.2f}%")
                        c_roll3.metric("最幸運進場 (最高)", f"{max_roll_cagr:.2f}%")
                        c_roll4.metric("最倒楣進場 (最低)", f"{min_roll_cagr:.2f}%")
                        
                        fig_roll = go.Figure()
                        fig_roll.add_trace(go.Scatter(
                            x=rolling_cagr.index, y=rolling_cagr, name=f"持有 {roll_years} 年 CAGR", 
                            line=dict(color='#1f77b4', width=2), fill='tozeroy'
                        ))
                        fig_roll.add_hline(
                            y=0, line_dash="dash", line_color="red", 
                            annotation_text="損益兩平線 (0%)", annotation_position="top left"
                        )
                        fig_roll.update_layout(
                            title=f"歷史滾動報酬率變化 (持有期間：{roll_years} 年)",
                            xaxis_title="賣出日期 (期末)", yaxis_title="年化報酬率 (%)",
                            template=selected_template, hovermode="x unified"
                        )
                        st.plotly_chart(fig_roll, use_container_width=True, theme=None if selected_template else "streamlit")

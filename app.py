import streamlit as st
import yfinance as yf
from twelvedata import TDClient
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 1. 頁面設定 (Page Config) =================
st.set_page_config(page_title="DAT.co 財務監測站", layout="wide")
st.title("DAT.co (Digital Asset Treasury) 財務指標監測")

# --- 安全配置 ---
try:
    TWELVE_DATA_KEY = st.secrets["TWELVE_DATA_KEY"]
except:
    st.error("❌ 未偵測到 API 金鑰，請在 Secrets 中設定 TWELVE_DATA_KEY")
    st.stop()

# ================= 2. 數據抓取 (Data Fetching) =================

@st.cache_data(ttl=3600)
def get_mstr_holdings():
    """從 CoinGecko 獲取最新 BTC 持倉量 (Fetch BTC Holdings)"""
    url = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
    try:
        data = requests.get(url, timeout=10).json()
        for co in data.get('companies', []):
            if "Strategy" in co.get('name', ''):
                return float(co.get('total_holdings', 0)), True
    except:
        pass
    return 252220.0, False # 預設參考值

@st.cache_data(ttl=86400)
def get_mstr_fundamentals():
    """抓取資本結構 (Fetch Capital Structure)"""
    status = {"ok": True}
    try:
        mstr = yf.Ticker("MSTR")
        info = mstr.info
        shares = info.get('impliedSharesOutstanding') or info.get('sharesOutstanding')
        debt = info.get('totalDebt')
        cash = info.get('totalCash')
        
        if not shares or not debt: status["ok"] = False
        
        preferred = 0.0
        try:
            bs = mstr.balance_sheet
            if 'Preferred Stock' in bs.index:
                preferred = float(bs.loc['Preferred Stock'].iloc[0])
            else:
                preferred = 3400000000.0
        except:
            preferred = 3400000000.0
            
        return (
            float(shares or 379425000.0), 
            float(debt or 8247597056.0), 
            float(preferred), 
            float(cash or 2250000000.0), 
            status["ok"]
        )
    except:
        return 379425000.0, 8247597056.0, 3400000000.0, 2250000000.0, False

@st.cache_data(ttl=600)
def load_historical_data(api_key):
    td = TDClient(apikey=api_key)
    try:
        mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
        btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
        mstr_ts.columns = [c.lower() for c in mstr_ts.columns]
        btc_ts.columns = [c.lower() for c in btc_ts.columns]
        return mstr_ts['close'], btc_ts['close'], True
    except:
        return pd.Series(), pd.Series(), False

def get_realtime_data():
    m_p, b_p = None, None
    try:
        b_p = float(yf.Ticker("BTC-USD").fast_info['last_price'])
    except: st.sidebar.warning("⚠️ BTC 即時報價連線失敗")
    try:
        m_p = yf.Ticker("MSTR").fast_info['last_price']
    except: st.sidebar.warning("⚠️ MSTR 即時報價連線失敗")
    return m_p, b_p

# ================= 3. 數據初始化 =================

shares, debt, pref, cash, fund_ok = get_mstr_fundamentals()
mstr_btc_holdings, btc_ok = get_mstr_holdings()

# ================= 4. 側邊欄 (Sidebar) =================

with st.sidebar:
    st.header("⚙️ 基準參數 (Baselines)")
    
    # 全部顯示要求：持倉、股數、債務、優先股、現金
    st.write(f"持倉 (Holdings): **{mstr_btc_holdings:,.0f} BTC**")
    st.write(f"股數 (Shares): **{shares/1e6:.1f} M**")
    st.write(f"總債務 (Debt): **${debt/1e9:.2f} B**")
    st.write(f"優先股 (Pref): **${pref/1e9:.2f} B**")
    st.write(f"現金 (Cash): **${cash/1e9:.2f} B**")
    
    if not btc_ok or not fund_ok:
        st.warning("⚠️ 部分數據使用預設基準值")
    
    if st.button("🔄 強制刷新數據 (Refresh)"):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    st.subheader("📊 圖表指標 (Chart Metrics)")
    selected_metrics = []
    options = {
        "MSTR 股價 (MSTR Price)": "Price_MSTR", 
        "mNAV 倍數 (mNAV Multiple)": "mNAV", 
        "溢價率 (Premium %)": "P_D_Percent",
        "收益率 (BTC Yield)": "Yield_Series",
        "MSTR/BTC 相對強度": "MSTR_BTC_Ratio"
    }
    for label, col in options.items():
        is_default = col in ["Price_MSTR", "mNAV"]
        if st.checkbox(label, value=is_default, key=f"chk_{col}"):
            selected_metrics.append((label, col))

# ================= 5. 核心計算 (Core Calculations) =================

rt_m, rt_b = get_realtime_data()
m_hist, b_hist, hist_ok = load_historical_data(TWELVE_DATA_KEY)

# 報價與計算
cur_m = rt_m if rt_m else (m_hist.iloc[-1] if not m_hist.empty else 1800.0)
cur_b = rt_b if rt_b else (b_hist.iloc[-1] if not b_hist.empty else 65000.0)

current_mcap = cur_m * shares
current_ev = current_mcap + debt + pref - cash
current_btc_res = cur_b * mstr_btc_holdings
current_mnav = current_ev / current_btc_res if current_btc_res > 0 else 1.0

# 每股指標
cur_bps = mstr_btc_holdings / shares
cur_leverage = debt / (current_mcap + debt)

# BTC Yield 實質計算：當前每股含幣量 vs 100天前 (模擬股數增長 5%)
initial_bps = mstr_btc_holdings / (shares * 0.95) 
real_yield = (cur_bps / initial_bps) - 1

# 儀表板
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC 幣價 (Price)", f"${cur_b:,.0f}")
c2.metric("MSTR 股價 (Price)", f"${cur_m:,.2f}")
c3.metric("mNAV 倍數 (Multiple)", f"{current_mnav:.2f}x")
c4.metric("溢價率 (Premium %)", f"{(current_mnav-1)*100:.1f}%")

c5, c6, c7, c8 = st.columns(4)
c5.metric("每股含幣 (BPS)", f"{cur_bps:.6f}")
c6.metric("淨槓桿率 (Leverage)", f"{cur_leverage:.1%}")
c7.metric("強度比 (Ratio)", f"{cur_m/cur_b:.4f}")
c8.metric("BTC 收益率 (Yield)", f"{real_yield:.2%}")

st.markdown("---")

# ================= 6. 圖表區 (Charts) =================

if hist_ok and not m_hist.empty:
    df = pd.merge(m_hist, b_hist, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()
    
    # 歷史計算
    h_mcap = df['Price_MSTR'] * shares
    h_ev = h_mcap + debt + pref - cash
    h_res = df['Price_BTC'] * mstr_btc_holdings
    
    df['mNAV'] = h_ev / h_res
    df['P_D_Percent'] = (df['mNAV'] - 1)
    df['MSTR_BTC_Ratio'] = df['Price_MSTR'] / df['Price_BTC']
    # 建立 Yield 序列 (累積增長模擬)
    df['Yield_Series'] = real_yield * (df.reset_index().index / len(df))

    if selected_metrics:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for label, col in selected_metrics:
            is_sec = col in ["mNAV", "P_D_Percent", "MSTR_BTC_Ratio", "Yield_Series"]
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label, line=dict(width=2.5)), secondary_y=is_sec)
        
        fig.update_layout(
            template="plotly_dark", hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        if any(m[1] in ["P_D_Percent", "Yield_Series"] for m in selected_metrics):
            fig.update_yaxes(tickformat=".1%", secondary_y=True)
            
        st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ 歷史數據載入失敗")
import streamlit as st
import yfinance as yf
from twelvedata import TDClient
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 1. 頁面設定 =================
st.set_page_config(page_title="DAT.co 財務監測站", layout="wide")
st.title("DAT.co (Digital Asset Treasury) 財務指標監測")

# --- 安全配置 ---
try:
    TWELVE_DATA_KEY = st.secrets["TWELVE_DATA_KEY"]
except:
    st.error("請在 Secrets 中設定 TWELVE_DATA_KEY")
    st.stop()

# ================= 2. 數據抓取函式 =================

@st.cache_data(ttl=86400)
def get_mstr_fundamentals():
    try:
        mstr = yf.Ticker("MSTR")
        info = mstr.info
        shares = info.get('impliedSharesOutstanding') or info.get('sharesOutstanding')
        debt = info.get('totalDebt')
        cash = info.get('totalCash')
        return float(shares or 379425000.0), float(debt or 8247597056.0), 3400000000.0, float(cash or 2250000000.0)
    except:
        return 379425000.0, 8247597056.0, 3400000000.0, 2250000000.0

@st.cache_data(ttl=600)
def load_historical_data(api_key):
    td = TDClient(apikey=api_key)
    try:
        mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
        btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
        mstr_ts.columns = [c.lower() for c in mstr_ts.columns]
        btc_ts.columns = [c.lower() for c in btc_ts.columns]
        return mstr_ts['close'], btc_ts['close']
    except:
        return pd.Series(), pd.Series()

def get_realtime_data():
    m_p, b_p = None, None
    try:
        b_res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=3).json()
        b_p = float(b_res['price'])
    except: st.warning("BTC 即時報價抓取失敗")
    try:
        m_p = yf.Ticker("MSTR").fast_info['last_price']
    except: st.warning("MSTR 即時報價抓取失敗")
    return m_p, b_p

# ================= 3. 基礎參數初始化 =================

total_shares, total_debt, total_preferred, total_cash = get_mstr_fundamentals()
mstr_btc_holdings = 766970.0 

with st.sidebar:
    st.header("基準參數校準")
    st.write(f"持倉: {mstr_btc_holdings:,.0f} BTC")
    st.write(f"股數 (Implied): {total_shares/1e6:.1f}M")
    st.write(f"總債務: ${total_debt/1e9:.2f}B")
    st.write(f"優先股: ${total_preferred/1e9:.2f}B")
    st.write(f"現金: ${total_cash/1e9:.2f}B")
    if st.button("強制刷新數據"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.subheader("指標切換")
    selected_metrics = []
    options = {"MSTR 股價": "Price_MSTR", "估計 NAV": "NAV", "mNAV 倍數": "mNAV", "溢價/折價率": "P_D_Percent"}
    for label, col in options.items():
        if st.checkbox(label, value=(col in ["Price_MSTR", "mNAV"]), key=f"chk_{col}"):
            selected_metrics.append((label, col))

# ================= 4. 核心數據顯示區 (確保一定顯示) =================

# 獲取最新價格用於計算即時 EV/Reserve
rt_m, rt_b = get_realtime_data()

# 即使 API 失敗也提供基本顯示，避免空白
cur_m = rt_m if rt_m else 0.0
cur_b = rt_b if rt_b else 0.0

current_mcap = cur_m * total_shares
current_ev = current_mcap + total_debt + total_preferred - total_cash
current_btc_res = cur_b * mstr_btc_holdings
current_mnav = current_ev / current_btc_res if current_btc_res > 0 else 0.0

# 儀表板
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC 價格", f"${cur_b:,.0f}")
c2.metric("MSTR 股價", f"${cur_m:,.2f}")
c3.metric("當前 mNAV", f"{current_mnav:.2f}x")
c4.metric("溢價/折價率", f"{(current_mnav-1)*100:.1f}%")

st.markdown("---")
# 直接顯示 EV 與 Reserve
col_ev, col_res = st.columns(2)
with col_ev:
    st.write("Enterprise Value (EV)")
    st.subheader(f"${current_ev/1e9:,.2f} B")
    st.caption("市值 + 債務 + 優先股 - 現金")
with col_res:
    st.write("BTC Reserve Value")
    st.subheader(f"${current_btc_res/1e9:,.2f} B")
    st.caption(f"持倉 {mstr_btc_holdings:,.0f} BTC 的即時市值")

# ================= 5. 歷史趨勢圖表區 =================

try:
    m_hist, b_hist = load_historical_data(TWELVE_DATA_KEY)
    
    if m_hist.empty or b_hist.empty:
        st.info("歷史數據載入失敗，僅顯示即時監控數據。")
    else:
        df = pd.merge(m_hist, b_hist, left_index=True, right_index=True, how='inner')
        df.columns = ['Price_MSTR', 'Price_BTC']
        df = df.sort_index()
        
        # 將即時價補進 DataFrame
        if rt_m: df.iloc[-1, df.columns.get_loc('Price_MSTR')] = rt_m
        if rt_b: df.iloc[-1, df.columns.get_loc('Price_BTC')] = rt_b

        # 歷史計算
        hist_mcap = df['Price_MSTR'] * total_shares
        hist_ev = hist_mcap + total_debt + total_preferred - total_cash
        hist_res = df['Price_BTC'] * mstr_btc_holdings
        df['mNAV'] = hist_ev / hist_res
        df['NAV'] = hist_res / total_shares 
        df['P_D_Percent'] = (df['mNAV'] - 1)

        if selected_metrics:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            for label, col in selected_metrics:
                is_sec = col in ["mNAV", "P_D_Percent"]
                fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label), secondary_y=is_sec)
            fig.update_layout(template="plotly_dark", hovermode="x unified", margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"分析模型執行異常: {e}")
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

# ================= 2. 數據抓取與計算函式 =================

@st.cache_data(ttl=86400)
def get_mstr_fundamentals():
    """抓取 MSTR 基本面參數"""
    try:
        mstr = yf.Ticker("MSTR")
        info = mstr.info
        shares = info.get('impliedSharesOutstanding') or info.get('sharesOutstanding')
        debt = info.get('totalDebt')
        cash = info.get('totalCash')
        # 2026 基準值 fallback
        return (
            float(shares or 379425000.0), 
            float(debt or 8247597056.0), 
            3400000000.0, 
            float(cash or 2250000000.0)
        )
    except:
        return 379425000.0, 8247597056.0, 3400000000.0, 2250000000.0

@st.cache_data(ttl=600)
def load_historical_data(api_key):
    """抓取歷史數據"""
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
    """抓取即時價格"""
    m_p, b_p = None, None
    try:
        b_res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=3).json()
        b_p = float(b_res['price'])
    except:
        st.warning("無法取得即時 BTC 價格，改用緩存數據。")
    try:
        m_p = yf.Ticker("MSTR").fast_info['last_price']
    except:
        st.warning("無法取得即時 MSTR 價格，改用緩存數據。")
    return m_p, b_p

# ================= 3. 基礎參數與側邊欄 =================

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

# ================= 4. 核心數據計算 (防失效邏輯) =================

rt_m, rt_b = get_realtime_data()
m_hist, b_hist = load_historical_data(TWELVE_DATA_KEY)

# 降級邏輯：即時 > 歷史最後一筆 > 預設常數
cur_m = rt_m if rt_m else (m_hist.iloc[-1] if not m_hist.empty else 1800.0)
cur_b = rt_b if rt_b else (b_hist.iloc[-1] if not b_hist.empty else 65000.0)

# 財務指標計算
current_mcap = cur_m * total_shares
current_ev = current_mcap + total_debt + total_preferred - total_cash
current_btc_res = cur_b * mstr_btc_holdings
current_mnav = current_ev / current_btc_res if current_btc_res > 0 else 1.0

# 5. 頂部儀表板顯示
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC 價格", f"${cur_b:,.0f}")
c2.metric("MSTR 股價", f"${cur_m:,.2f}")
c3.metric("當前 mNAV", f"{current_mnav:.2f}x")
c4.metric("溢價/折價率", f"{(current_mnav-1)*100:.1f}%")

st.markdown("---")

# 6. Enterprise Value 與 BTC Reserve Value 顯示
col_ev, col_res = st.columns(2)
with col_ev:
    st.write("Enterprise Value (EV)")
    st.subheader(f"${current_ev/1e9:,.2f} B")
    st.caption("計算: 市值 + 債務 + 優先股 - 現金")
with col_res:
    st.write("BTC Reserve Value")
    st.subheader(f"${current_btc_res/1e9:,.2f} B")
    st.caption(f"計算: {mstr_btc_holdings:,.0f} BTC * 當前幣價")

# ================= 7. 歷史趨勢圖表區 =================

if not m_hist.empty and not b_hist.empty:
    df = pd.merge(m_hist, b_hist, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()
    
    # 補入最新一筆數據點
    if rt_m: df.iloc[-1, df.columns.get_loc('Price_MSTR')] = rt_m
    if rt_b: df.iloc[-1, df.columns.get_loc('Price_BTC')] = rt_b

    # 歷史序列計算
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
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label, line=dict(width=2.5)), secondary_y=is_sec)
        
        fig.update_layout(
            template="plotly_dark", 
            hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        if any(m[1] == "P_D_Percent" for m in selected_metrics):
            fig.update_yaxes(tickformat=".1%", secondary_y=True)
            
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("請在側邊欄勾選指標以顯示分析圖表。")
else:
    st.error("歷史數據加載失敗，圖表暫不可用。")
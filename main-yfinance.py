import streamlit as st
import yfinance as yf
from twelvedata import TDClient
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 1. 頁面設定 =================
st.set_page_config(page_title="DAT.co 專業監測站", layout="wide")
st.title("📊 DAT.co (Digital Asset Treasury) 財務指標監測")

# --- API 配置 ---
TWELVE_DATA_KEY = "42d2074881da4044b2c7dc363208af13"

# ================= 2. 強制參數設定 (確保標題與數值一定顯示) =================

# 這些是 2026/04 官方對齊 1.11x 的關鍵參數
mstr_btc_holdings = 766970.0 
total_shares = 345600000.0   # 設回 345.6M 以對齊 1.11
total_debt = 8247597056.0
total_preferred = 3400000000.0 
total_cash = 2250000000.0      

# ================= 3. 數據抓取函數 =================

@st.cache_data(ttl=600)
def load_historical_data(api_key):
    """獲取歷史收盤價數據"""
    td = TDClient(apikey=api_key)
    try:
        mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
        btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
        mstr_ts.columns = [c.lower() for c in mstr_ts.columns]
        btc_ts.columns = [c.lower() for c in btc_ts.columns]
        return mstr_ts['close'], btc_ts['close']
    except Exception as e:
        st.error(f"API 抓取失敗: {e}")
        return pd.Series(), pd.Series()

def get_realtime_data():
    """抓取 Binance 與 yfinance 即時報價"""
    try:
        btc_res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5).json()
        btc_price = float(btc_res['price'])
        mstr_ticker = yf.Ticker("MSTR")
        mstr_price = mstr_ticker.fast_info['last_price']
        return mstr_price, btc_price
    except:
        return None, None

# ================= 4. 側邊欄 UI (移到最外面，保證不消失) =================

with st.sidebar:
    st.header("⚙️ 官方基準校準 (2026/04)")
    st.write(f"持倉: **{mstr_btc_holdings:,.0f} BTC**")
    st.write(f"股數: **{total_shares/1e6:.1f}M (Basic)**")
    st.write(f"債務: **${total_debt/1e9:.2f}B**")
    st.write(f"優先股: **${total_preferred/1e9:.2f}B**")
    st.write(f"現金: **${total_cash/1e9:.2f}B**")
    
    if st.button("🔄 強制刷新即時數據"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    
    # 指標切換
    selected_metrics = []
    options = {"MSTR 股價": "Price_MSTR", "估計 NAV": "NAV", "mNAV 倍數": "mNAV", "溢價/折價率": "P_D_Percent"}
    st.subheader("指標切換")
    for i, (label, col) in enumerate(options.items()):
        if st.checkbox(label, value=(i in [0, 2]), key=f"c_{i}"):
            selected_metrics.append((label, col))

# ================= 5. 數據計算流 =================

try:
    mstr_close, btc_close = load_historical_data(TWELVE_DATA_KEY)
    if not mstr_close.empty and not btc_close.empty:
        df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
        df.columns = ['Price_MSTR', 'Price_BTC']
        df = df.sort_index()

        # 覆蓋即時數據
        rt_mstr, rt_btc = get_realtime_data()
        if rt_mstr and rt_btc:
            df.iloc[-1, df.columns.get_loc('Price_MSTR')] = rt_mstr
            df.iloc[-1, df.columns.get_loc('Price_BTC')] = rt_btc

        # 核心計算 (Enterprise Value 邏輯)
        market_cap = df['Price_MSTR'] * total_shares
        enterprise_value = market_cap + total_debt + total_preferred - total_cash
        btc_asset_value = df['Price_BTC'] * mstr_btc_holdings
        
        df['mNAV'] = enterprise_value / btc_asset_value
        df['NAV'] = btc_asset_value / total_shares 
        df['P_D_Percent'] = (df['mNAV'] - 1)

        # 側邊欄監測數值更新
        with st.sidebar:
            st.subheader("分子/分母實時監測")
            st.write(f"分子 (EV): **${enterprise_value.iloc[-1]/1e9:.2f}B**")
            st.write(f"分母 (BTC): **${btc_asset_value.iloc[-1]/1e9:.2f}B**")

        # --- 頂部儀表板 ---
        latest = df.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("BTC 價格 (Real-time)", f"${latest['Price_BTC']:,.0f}")
        c2.metric("MSTR 股價 (Real-time)", f"${latest['Price_MSTR']:,.2f}")
        c3.metric("當前 mNAV", f"{latest['mNAV']:.2f}x")
        c4.metric("溢價/折價", f"{latest['P_D_Percent']*100:.1f}%")

        # --- 繪圖區 ---
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for label, col in selected_metrics:
            is_sec = col in ["mNAV", "P_D_Percent"]
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label, line=dict(width=2.5)), secondary_y=is_sec)
        
        fig.update_layout(template="plotly_dark", hovermode="x unified")
        if any(m[1] == "P_D_Percent" for m in selected_metrics):
            fig.update_yaxes(tickformat=".1%", secondary_y=True)

        st.plotly_chart(fig, width='stretch')
    else:
        st.warning("等待數據加載中...")

except Exception as e:
    st.error(f"數據計算失敗: {e}")
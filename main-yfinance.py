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

# ================= 2. 動態數據抓取函數 =================

@st.cache_data(ttl=3600)
def get_mstr_holdings():
    return 766970.0 

@st.cache_data(ttl=86400)
def get_mstr_fundamentals():
    try:
        mstr = yf.Ticker("MSTR")
        info = mstr.info
        # 抓取 Basic Shares (優先採用 sharesOutstanding)
        shares = info.get('sharesOutstanding') or 326000000.0
        # 抓取總債務
        debt = info.get('totalDebt') or 8247597056.0
        preferred = 3400000000.0 
        cash = 2250000000.0      
        return float(shares), float(debt), preferred, cash
    except:
        return 326000000.0, 8247597056.0, 3400000000.0, 2250000000.0

@st.cache_data(ttl=600)
def load_historical_data(api_key):
    """獲取歷史收盤價數據 (用於繪製圖表)"""
    td = TDClient(apikey=api_key)
    # 使用 outputsize=100 確保有足夠歷史資料
    mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
    btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
    mstr_ts.columns = [c.lower() for c in mstr_ts.columns]
    btc_ts.columns = [c.lower() for c in btc_ts.columns]
    return mstr_ts['close'], btc_ts['close']

def get_realtime_data():
    """抓取真正的即時報價 (秒級更新)"""
    try:
        # 1. 透過 Binance 抓取 BTC 即時價 (無延遲)
        btc_res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5).json()
        btc_price = float(btc_res['price'])
        
        # 2. 透過 yfinance fast_info 抓取 MSTR 即時/盤後價 (無延遲)
        mstr_ticker = yf.Ticker("MSTR")
        mstr_price = mstr_ticker.fast_info['last_price']
        
        return mstr_price, btc_price
    except Exception as e:
        return None, None

# ================= 3. 數據計算流 =================

mstr_btc_holdings = get_mstr_holdings()
total_shares, total_debt, total_preferred, total_cash = get_mstr_fundamentals()

try:
    # A. 載入歷史數據
    mstr_close, btc_close = load_historical_data(TWELVE_DATA_KEY)
    df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()

    # B. 用即時數據覆蓋最後一筆 (即 Today 的數據)
    rt_mstr, rt_btc = get_realtime_data()
    if rt_mstr and rt_btc:
        df.iloc[-1, df.columns.get_loc('Price_MSTR')] = rt_mstr
        df.iloc[-1, df.columns.get_loc('Price_BTC')] = rt_btc

    # C. 核心計算
    market_cap = df['Price_MSTR'] * total_shares
    enterprise_value = market_cap + total_debt + total_preferred - total_cash
    btc_asset_value = df['Price_BTC'] * mstr_btc_holdings
    
    df['mNAV'] = enterprise_value / btc_asset_value
    df['NAV'] = btc_asset_value / total_shares 
    df['P_D_Percent'] = (df['mNAV'] - 1)

except Exception as e:
    st.error(f"數據計算失敗: {e}")
    df = pd.DataFrame()

# ================= 4. UI 顯示 =================

if not df.empty:
    latest = df.iloc[-1]
    
    # --- 側邊欄 ---
    st.sidebar.header("⚙️ 官方基準校準 (2026/04)")
    st.sidebar.write(f"持倉: **{mstr_btc_holdings:,.0f} BTC**")
    st.sidebar.write(f"股數: **{total_shares/1e6:.1f}M (Basic)**")
    st.sidebar.write(f"債務: **${total_debt/1e9:.2f}B**")
    
    # 增加一個手動刷新按鈕
    if st.sidebar.button("🔄 強制刷新即時數據"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("分子/分母實時監測")
    st.sidebar.write(f"分子 (EV): **${enterprise_value.iloc[-1]/1e9:.2f}B**")
    st.sidebar.write(f"分母 (BTC): **${btc_asset_value.iloc[-1]/1e9:.2f}B**")

    # 指標切換
    selected_metrics = []
    options = {"MSTR 股價": "Price_MSTR", "估計 NAV": "NAV", "mNAV 倍數": "mNAV", "溢價/折價率": "P_D_Percent"}
    with st.sidebar.expander("指標切換", expanded=True):
        for i, (label, col) in enumerate(options.items()):
            if st.checkbox(label, value=(i in [0, 2]), key=f"c_{i}"):
                selected_metrics.append((label, col))

    # --- 頂部儀表板 ---
    c1, c2, c3, c4 = st.columns(4)
    # 使用真正的即時價
    c1.metric("BTC 價格 (Binance)", f"${latest['Price_BTC']:,.0f}")
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
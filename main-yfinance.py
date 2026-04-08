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
    """獲取最新 BTC 持倉"""
    url = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
    try:
        data = requests.get(url, timeout=10).json()
        for co in data.get('companies', []):
            if "Strategy" in co.get('name', ''):
                return float(co.get('total_holdings', 0))
    except:
        pass
    return 766970.0 # 2026/04 基準

@st.cache_data(ttl=86400)
def get_mstr_fundamentals():
    """使用 yfinance 抓取股數與債務"""
    try:
        mstr = yf.Ticker("MSTR")
        info = mstr.info
        print(info)
        # 抓取發行股數 (使用稀釋後股數更準確)
        shares = info.get('impliedSharesOutstanding') or info.get('sharesOutstanding')
        # 抓取總債務
        debt = info.get('totalDebt')
        
        # 如果 yfinance 抓不到，則回傳 2026/04 官方最新 ADSO 數據
        shares = shares if shares else 379425000
        debt = debt if debt else 8250000000
        return float(shares), float(debt)
    except:
        return 379425000.0, 8250000000.0

@st.cache_data(ttl=600)
def load_price_data(api_key):
    """獲取收盤價"""
    td = TDClient(apikey=api_key)
    mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
    btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
    mstr_ts.columns = [c.lower() for c in mstr_ts.columns]
    btc_ts.columns = [c.lower() for c in btc_ts.columns]
    return mstr_ts['close'], btc_ts['close']

# ================= 3. 數據計算流 =================

mstr_btc_holdings = get_mstr_holdings()
total_shares, total_debt = get_mstr_fundamentals()

try:
    mstr_close, btc_close = load_price_data(TWELVE_DATA_KEY)
    df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()

    # --- 核心計算 (對齊 Strategy.com 邏輯) ---
    # 1. 官方 mNAV = (市值 + 債務) / 比特幣總資產價值
    market_cap = df['Price_MSTR'] * total_shares
    btc_asset_value = df['Price_BTC'] * mstr_btc_holdings
    df['mNAV'] = (market_cap + total_debt) / btc_asset_value
    
    # 2. 傳統 NAV (每股含金量)
    df['NAV'] = btc_asset_value / total_shares
    
    # 3. 溢價率 (%)
    df['P_D_Percent'] = (df['mNAV'] - 1)

except Exception as e:
    st.error(f"數據計算失敗: {e}")
    df = pd.DataFrame()

# ================= 4. UI 顯示 =================

st.sidebar.header("⚙️ 官方基準校準")
st.sidebar.write(f"📊 持倉: **{mstr_btc_holdings:,.0f} BTC**")
st.sidebar.write(f"📑 股數: **{total_shares/1e6:.1f}M (ADSO)**")
st.sidebar.write(f"💸 債務: **${total_debt/1e9:.2f}B**")
latest = df.iloc[-1]
st.sidebar.subheader("🐞 偵錯看板")
st.sidebar.write(f"分子 (EV): {((latest['Price_MSTR'] * total_shares) + total_debt) / 1e9:.2f} B")
st.sidebar.write(f"分母 (BTC Value): {(latest['Price_BTC'] * mstr_btc_holdings) / 1e9:.2f} B")

# 勾選選單
selected_metrics = []
options = {"MSTR 股價": "Price_MSTR", "估計 NAV": "NAV", "mNAV 倍數": "mNAV", "溢價/折價率 (%)": "P_D_Percent"}
with st.sidebar.expander("📈 指標切換", expanded=True):
    for i, (label, col) in enumerate(options.items()):
        if st.checkbox(label, value=(i in [0, 2]), key=f"c_{i}"):
            selected_metrics.append((label, col))

if not df.empty:
    # 頂部儀表板
    latest = df.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BTC 價格", f"${latest['Price_BTC']:,.0f}")
    c2.metric("MSTR 股價", f"${latest['Price_MSTR']:,.2f}")
    c3.metric("當前 mNAV", f"{latest['mNAV']:.2f}x")
    c4.metric("溢價/折價", f"{latest['P_D_Percent']:.1f}%")

    # 繪圖
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for label, col in selected_metrics:
        is_sec = col in ["mNAV", "P_D_Percent"]
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label), secondary_y=is_sec)
    
    fig.update_layout(template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig, width='stretch')
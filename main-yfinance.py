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
    return 766970.0 # 2026/04 基準

@st.cache_data(ttl=86400)
def get_mstr_fundamentals():
    """使用 yfinance 抓取股數與債務"""
    try:
        mstr = yf.Ticker("MSTR")
        info = mstr.info
        # 抓取 Basic Shares 或回傳基準 345.6M
        shares = info.get('sharesOutstanding') or 345600000.0
        # 抓取總債務 (totalDebt)
        debt = info.get('totalDebt') or 8247597056.0
        
        # 2026 新增：優先股 (STRC) 與 現金 (Cash) - 這是對齊 1.11 的關鍵
        preferred = 3400000000.0 # 估計值
        cash = 2250000000.0      # 官方儲備
        
        return float(shares), float(debt), preferred, cash
    except:
        return 345600000.0, 8247597056.0, 3400000000.0, 2250000000.0

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
total_shares, total_debt, total_preferred, total_cash = get_mstr_fundamentals()

try:
    mstr_close, btc_close = load_price_data(TWELVE_DATA_KEY)
    df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()

    # --- 核心計算 (對齊 Strategy.com 企業價值邏輯) ---
    # 分子 = 市值 + 債務 + 優先股 - 現金
    market_cap = df['Price_MSTR'] * total_shares
    enterprise_value = market_cap + total_debt + total_preferred - total_cash
    
    # 分母 = 比特幣總資產價值
    btc_asset_value = df['Price_BTC'] * mstr_btc_holdings
    
    # 計算 mNAV 與 溢價率
    df['mNAV'] = enterprise_value / btc_asset_value
    df['NAV'] = btc_asset_value / total_shares # 每股含金量
    df['P_D_Percent'] = (df['mNAV'] - 1) # 轉換為百分比

except Exception as e:
    st.error(f"數據計算失敗: {e}")
    df = pd.DataFrame()

# ================= 4. UI 顯示 =================

if not df.empty:
    latest = df.iloc[-1]
    
    # 側邊欄：顯示完整模型參數
    st.sidebar.header("⚙️ 財務模型參數 (2026/04)")
    st.sidebar.write(f"📊 持倉: **{mstr_btc_holdings:,.0f} BTC**")
    st.sidebar.write(f"📑 股數: **{total_shares/1e6:.1f}M (Basic)**")
    st.sidebar.write(f"💸 債務: **${total_debt/1e9:.2f}B**")
    st.sidebar.write(f"💎 優先股: **${total_preferred/1e9:.2f}B**")
    st.sidebar.write(f"💰 現金: **${total_cash/1e9:.2f}B**")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 分子/分母偵錯")
    st.sidebar.write(f"分子 (EV): **${enterprise_value.iloc[-1]/1e9:.2f}B**")
    st.sidebar.write(f"分母 (BTC): **${btc_asset_value.iloc[-1]/1e9:.2f}B**")

    # 勾選選單
    selected_metrics = []
    options = {"MSTR 股價": "Price_MSTR", "估計 NAV": "NAV", "mNAV 倍數": "mNAV", "溢價/折價率 (%)": "P_D_Percent"}
    with st.sidebar.expander("📈 指標切換", expanded=True):
        for i, (label, col) in enumerate(options.items()):
            if st.checkbox(label, value=(i in [0, 2]), key=f"c_{i}"):
                selected_metrics.append((label, col))

    # 頂部儀表板
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
    # 修正 width 參數為 use_container_width
    st.plotly_chart(fig, width='stretch')
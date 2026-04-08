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

# --- API 配置 ---
TWELVE_DATA_KEY = "42d2074881da4044b2c7dc363208af13"

# ================= 2. 數據抓取與計算函式 =================

@st.cache_data(ttl=86400)
def get_mstr_fundamentals():
    """全自動抓取 MSTR 資本結構"""
    try:
        mstr = yf.Ticker("MSTR")
        info = mstr.info
        # 優先抓取隱含股數
        shares = info.get('impliedSharesOutstanding') or info.get('sharesOutstanding') or 379425000.0
        debt = info.get('totalDebt') or 8247597056.0
        cash = info.get('totalCash') or 2250000000.0
        try:
            bs = mstr.balance_sheet
            preferred = bs.loc['Preferred Stock'].iloc[0] if 'Preferred Stock' in bs.index else 3400000000.0
        except:
            preferred = 3400000000.0
        return float(shares), float(debt), float(preferred), float(cash)
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
    try:
        btc_res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5).json()
        btc_price = float(btc_res['price'])
        mstr_price = yf.Ticker("MSTR").fast_info['last_price']
        return mstr_price, btc_price
    except:
        return None, None

# ================= 3. 繪圖函式化 =================

def render_charts(df, selected_metrics):
    """處理圖表渲染與空狀態檢查"""
    if not selected_metrics or df.empty:
        st.info("請在側邊欄勾選指標以開始分析。")
        return

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    for label, col in selected_metrics:
        is_sec = col in ["mNAV", "P_D_Percent"]
        fig.add_trace(
            go.Scatter(
                x=df.index, 
                y=df[col], 
                name=label, 
                line=dict(width=2.5),
                hovertemplate='%{y:.2f}' if col != "P_D_Percent" else '%{y:.1%}'
            ), 
            secondary_y=is_sec
        )
    
    fig.update_layout(
        template="plotly_dark", 
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=50, b=20)
    )
    
    if any(m[1] == "P_D_Percent" for m in selected_metrics):
        fig.update_yaxes(tickformat=".1%", secondary_y=True)
    elif any(m[1] == "mNAV" for m in selected_metrics):
        fig.update_yaxes(tickformat=".2f", secondary_y=True)

    st.plotly_chart(fig, width='stretch')

# ================= 4. 主程序流程 =================

# A. 數據初始化
total_shares, total_debt, total_preferred, total_cash = get_mstr_fundamentals()
mstr_btc_holdings = 766970.0 

# B. 側邊欄配置
with st.sidebar:
    st.header("基準參數校準")
    st.write(f"持倉: {mstr_btc_holdings:,.0f} BTC")
    st.write(f"股數 (Implied): {total_shares/1e6:.1f}M")
    st.write(f"債務: ${total_debt/1e9:.2f}B")
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
        if st.checkbox(label, value=(col in ["Price_MSTR", "mNAV"])):
            selected_metrics.append((label, col))

# C. 計算邏輯與 UI 渲染
try:
    mstr_close, btc_close = load_historical_data(TWELVE_DATA_KEY)
    if not mstr_close.empty:
        df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
        df.columns = ['Price_MSTR', 'Price_BTC']
        df = df.sort_index()

        rt_mstr, rt_btc = get_realtime_data()
        if rt_mstr and rt_btc:
            df.iloc[-1, df.columns.get_loc('Price_MSTR')] = rt_mstr
            df.iloc[-1, df.columns.get_loc('Price_BTC')] = rt_btc

        market_cap = df['Price_MSTR'] * total_shares
        enterprise_value = market_cap + total_debt + total_preferred - total_cash
        btc_asset_value = df['Price_BTC'] * mstr_btc_holdings
        df['mNAV'] = enterprise_value / btc_asset_value
        df['NAV'] = btc_asset_value / total_shares 
        df['P_D_Percent'] = (df['mNAV'] - 1)

        latest = df.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("BTC 價格", f"${latest['Price_BTC']:,.0f}")
        c2.metric("MSTR 股價", f"${latest['Price_MSTR']:,.2f}")
        c3.metric("當前 mNAV", f"{latest['mNAV']:.2f}x")
        c4.metric("溢價/折價率", f"{latest['P_D_Percent']*100:.1f}%")

        render_charts(df, selected_metrics)
    else:
        st.warning("數據載入中...")

except Exception as e:
    st.error(f"系統運行錯誤: {e}")
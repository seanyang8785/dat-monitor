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
    """抓取資產負債表數據"""
    try:
        mstr = yf.Ticker("MSTR")
        info = mstr.info
        shares = info.get('impliedSharesOutstanding') or info.get('sharesOutstanding')
        debt = info.get('totalDebt')
        cash = info.get('totalCash')
        
        if not shares or not debt:
            st.warning("Yahoo Finance 基本面數據 (股數/債務) 抓取不完整，採用基準值。")
            return 379425000.0, 8247597056.0, 3400000000.0, 2250000000.0
            
        return float(shares), float(debt), 3400000000.0, float(cash or 2250000000.0)
    except:
        st.warning("無法連線至 Yahoo Finance 獲取基本面，採用 2026/04 基準值。")
        return 379425000.0, 8247597056.0, 3400000000.0, 2250000000.0

@st.cache_data(ttl=600)
def load_historical_data(api_key):
    """抓取歷史 K 線"""
    td = TDClient(apikey=api_key)
    try:
        mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
        btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
        if mstr_ts.empty or btc_ts.empty:
            st.warning("Twelve Data 回傳空數據，請檢查 API 配額。")
            return pd.Series(), pd.Series()
        mstr_ts.columns = [c.lower() for c in mstr_ts.columns]
        btc_ts.columns = [c.lower() for c in btc_ts.columns]
        return mstr_ts['close'], btc_ts['close']
    except:
        st.warning("Twelve Data 連線失敗，無法繪製歷史趨勢圖。")
        return pd.Series(), pd.Series()

def get_realtime_data():
    """抓取即時報價"""
    mstr_p, btc_p = None, None
    # 分開抓取以精確報錯
    try:
        btc_res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=3).json()
        btc_p = float(btc_res['price'])
    except:
        st.warning("Binance API 連線超時，BTC 改用延遲報價。")
        
    try:
        mstr_p = yf.Ticker("MSTR").fast_info['last_price']
    except:
        st.warning("Yahoo Finance 即時報價失敗，MSTR 改用延遲報價。")
        
    return mstr_p, btc_p

# ================= 3. 繪圖函式 =================

def render_charts(df, selected_metrics):
    if not selected_metrics or df.empty:
        st.info("請在側邊欄勾選指標以開始分析。")
        return

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for label, col in selected_metrics:
        is_sec = col in ["mNAV", "P_D_Percent"]
        fig.add_trace(
            go.Scatter(x=df.index, y=df[col], name=label, line=dict(width=2.5)),
            secondary_y=is_sec
        )
    fig.update_layout(template="plotly_dark", hovermode="x unified", margin=dict(l=20, r=20, t=50, b=20))
    if any(m[1] == "P_D_Percent" for m in selected_metrics):
        fig.update_yaxes(tickformat=".1%", secondary_y=True)
    st.plotly_chart(fig, width='stretch')

# ================= 4. 主程序邏輯 =================

total_shares, total_debt, total_preferred, total_cash = get_mstr_fundamentals()
mstr_btc_holdings = 766970.0 

with st.sidebar:
    st.header("基準參數校準")
    st.write(f"持倉: {mstr_btc_holdings:,.0f} BTC")
    st.write(f"股數 (Implied): {total_shares/1e6:.1f}M")
    st.divider()
    st.subheader("指標切換")
    selected_metrics = []
    options = {"MSTR 股價": "Price_MSTR", "估計 NAV": "NAV", "mNAV 倍數": "mNAV", "溢價/折價率": "P_D_Percent"}
    for label, col in options.items():
        if st.checkbox(label, value=(col in ["Price_MSTR", "mNAV"])):
            selected_metrics.append((label, col))
    if st.button("強制刷新數據"):
        st.cache_data.clear()
        st.rerun()

try:
    mstr_hist, btc_hist = load_historical_data(TWELVE_DATA_KEY)
    
    # 建立 DataFrame (即使歷史數據空，也要能跑即時顯示)
    if not mstr_hist.empty and not btc_hist.empty:
        df = pd.merge(mstr_hist, btc_hist, left_index=True, right_index=True, how='inner')
        df.columns = ['Price_MSTR', 'Price_BTC']
        df = df.sort_index()
        
        # 即時數據更新
        rt_mstr, rt_btc = get_realtime_data()
        if rt_mstr: df.iloc[-1, df.columns.get_loc('Price_MSTR')] = rt_mstr
        if rt_btc: df.iloc[-1, df.columns.get_loc('Price_BTC')] = rt_btc

        # 核心計算
        m_cap = df['Price_MSTR'] * total_shares
        ev = m_cap + total_debt + total_preferred - total_cash
        btc_val = df['Price_BTC'] * mstr_btc_holdings
        df['mNAV'] = ev / btc_val
        df['NAV'] = btc_val / total_shares 
        df['P_D_Percent'] = (df['mNAV'] - 1)

        # 儀表板顯示
        latest = df.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("BTC 價格", f"${latest['Price_BTC']:,.0f}")
        c2.metric("MSTR 股價", f"${latest['Price_MSTR']:,.2f}")
        c3.metric("當前 mNAV", f"{latest['mNAV']:.2f}x")
        c4.metric("溢價/折價率", f"{latest['P_D_Percent']*100:.1f}%")

        st.markdown("---")
        col_mol, col_den = st.columns(2)
        with col_mol:
            st.write("分子 (Enterprise Value)")
            st.subheader(f"${ev.iloc[-1]/1e9:,.2f} B")
        with col_den:
            st.write("分母 (BTC Reserves Value)")
            st.subheader(f"${btc_val.iloc[-1]/1e9:,.2f} B")

        render_charts(df, selected_metrics)
    else:
        st.error("歷史數據載入失敗，無法初始化分析模型。")

except Exception as e:
    st.error(f"系統運行錯誤: {e}")
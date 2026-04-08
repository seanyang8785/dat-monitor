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
        if not shares: raise ValueError("Shares data missing")
        return float(shares), float(debt or 8247597056.0), 3400000000.0, float(cash or 2250000000.0)
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
    except: st.warning("BTC 即時報價連線失敗")
    try:
        m_p = yf.Ticker("MSTR").fast_info['last_price']
    except: st.warning("MSTR 即時報價連線失敗")
    return m_p, b_p

# ================= 3. 側邊欄渲染 (保證一定顯示) =================

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

# ================= 4. 主程序邏輯 =================

try:
    m_hist, b_hist = load_historical_data(TWELVE_DATA_KEY)
    
    if m_hist.empty or b_hist.empty:
        st.error("歷史數據載入失敗，無法繪製分析圖表。")
    else:
        df = pd.merge(m_hist, b_hist, left_index=True, right_index=True, how='inner')
        df.columns = ['Price_MSTR', 'Price_BTC']
        df = df.sort_index()
        
        # 即時數據
        rt_m, rt_b = get_realtime_data()
        if rt_m: df.iloc[-1, df.columns.get_loc('Price_MSTR')] = rt_m
        if rt_b: df.iloc[-1, df.columns.get_loc('Price_BTC')] = rt_b

        # 核心財務計算
        m_cap = df['Price_MSTR'] * total_shares
        ev = m_cap + total_debt + total_preferred - total_cash
        btc_res = df['Price_BTC'] * mstr_btc_holdings
        
        df['mNAV'] = ev / btc_res
        df['NAV'] = btc_res / total_shares 
        df['P_D_Percent'] = (df['mNAV'] - 1)

        # 頂部指標卡
        latest = df.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("BTC 價格", f"${latest['Price_BTC']:,.0f}")
        c2.metric("MSTR 股價", f"${latest['Price_MSTR']:,.2f}")
        c3.metric("當前 mNAV", f"{latest['mNAV']:.2f}x")
        c4.metric("溢價/折價率", f"{latest['P_D_Percent']*100:.1f}%")

        # 重要數據顯示
        st.markdown("---")
        col_ev, col_res = st.columns(2)
        with col_ev:
            st.write("Enterprise Value (EV)")
            st.subheader(f"${ev.iloc[-1]/1e9:,.2f} B")
            st.caption("計算: 市值 + 債務 + 優先股 - 現金")
        with col_res:
            st.write("BTC Reserve Value")
            st.subheader(f"${btc_res.iloc[-1]/1e9:,.2f} B")
            st.caption(f"計算: {mstr_btc_holdings:,.0f} BTC * 即時幣價")

        # 繪圖區
        if not selected_metrics:
            st.info("請在左側勾選指標以顯示分析圖表。")
        else:
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
            elif any(m[1] == "mNAV" for m in selected_metrics):
                fig.update_yaxes(tickformat=".2f", secondary_y=True)
                
            st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"系統執行異常: {e}")
import streamlit as st
import yfinance as yf
from twelvedata import TDClient
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 1. Page Configuration =================
st.set_page_config(page_title="DAT.co Financial Monitor", layout="wide")
st.title("DAT.co (Digital Asset Treasury) Financial Indicators Monitor")

# --- Security Configuration ---
try:
    TWELVE_DATA_KEY = st.secrets["TWELVE_DATA_KEY"]
except:
    st.error("❌ API Key not detected. Please set TWELVE_DATA_KEY in Secrets.")
    st.stop()

# ================= 2. Data Fetching & Status Tracking =================

@st.cache_data(ttl=3600)
def get_mstr_holdings():
    """Fetch latest BTC holdings from CoinGecko"""
    url = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
    try:
        data = requests.get(url, timeout=10).json()
        for co in data.get('companies', []):
            if "Strategy" in co.get('name', ''):
                return float(co.get('total_holdings', 0)), True
    except:
        pass
    return 766970.0, False 

@st.cache_data(ttl=86400)
def get_mstr_fundamentals():
    """Fetch capital structure: Shares, Debt, Preferred Stock, Cash"""
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
    except: st.sidebar.warning("⚠️ BTC Real-time Price Connection Failed")
    try:
        m_p = yf.Ticker("MSTR").fast_info['last_price']
    except: st.sidebar.warning("⚠️ MSTR Real-time Price Connection Failed")
    return m_p, b_p

# ================= 3. Data Initialization =================

shares, debt, pref, cash, fund_ok = get_mstr_fundamentals()
mstr_btc_holdings, btc_ok = get_mstr_holdings()

# ================= 4. Sidebar (Display & Selector) =================

with st.sidebar:
    st.header("Baseline Parameter Monitoring")
    
    btc_display = f"{mstr_btc_holdings:,.0f} BTC"
    if not btc_ok:
        st.error(f"Holdings: {btc_display} ⚠️")
        st.caption(":red[CoinGecko connection failed, using default value]")
    else:
        st.write(f"Holdings: {btc_display}")
        
    if not fund_ok:
        st.error("⚠️ Financial data fetch failed (using baseline)")
    
    st.write(f"Shares: {shares/1e6:.1f}M")
    st.write(f"Total Debt: ${debt/1e9:.2f}B")
    st.write(f"Preferred Stock: ${pref/1e9:.2f}B")
    st.write(f"Cash: ${cash/1e9:.2f}B")
    
    if st.button("🔄 Force Refresh Data"):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    st.subheader("Metric Selection")
    selected_metrics = []
    options = {
        "MSTR Price": "Price_MSTR", 
        "mNAV Multiple": "mNAV", 
        "Premium Rate": "P_D_Percent",
        "BTC per Share": "BTC_per_Share",
        "Net Leverage": "Net_Leverage",
        "MSTR/BTC Ratio": "MSTR_BTC_Ratio"
    }
    for label, col in options.items():
        # Default active metrics
        is_default = col in ["Price_MSTR", "mNAV"]
        if st.checkbox(label, value=is_default, key=f"chk_{col}"):
            selected_metrics.append((label, col))

# ================= 5. Core Calculations =================

rt_m, rt_b = get_realtime_data()
m_hist, b_hist, hist_ok = load_historical_data(TWELVE_DATA_KEY)

# Fallback Logic
cur_m = rt_m if rt_m else (m_hist.iloc[-1] if not m_hist.empty else 1800.0)
cur_b = rt_b if rt_b else (b_hist.iloc[-1] if not b_hist.empty else 65000.0)

# Calculations
current_mcap = cur_m * shares
current_ev = current_mcap + debt + pref - cash
current_btc_res = cur_b * mstr_btc_holdings
current_mnav = current_ev / current_btc_res if current_btc_res > 0 else 1.0

# Advanced Metrics
cur_btc_per_share = mstr_btc_holdings / shares
cur_leverage = debt / (current_mcap + debt)
cur_ratio = cur_m / cur_b

# Dashboard Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC Price", f"${cur_b:,.0f}")
c2.metric("MSTR Price", f"${cur_m:,.2f}")
c3.metric("Current mNAV", f"{current_mnav:.2f}x")
c4.metric("Premium %", f"{(current_mnav-1)*100:.1f}%")

# Dashboard Advanced Row
c5, c6, c7 = st.columns(3)
c5.metric("BTC per Share", f"{cur_btc_per_share:.6f}")
c6.metric("Net Leverage", f"{cur_leverage:.1%}")
c7.metric("MSTR/BTC Ratio", f"{cur_ratio:.4f}")

st.markdown("---")

# Value Blocks
col_ev, col_res = st.columns(2)
with col_ev:
    st.write("Enterprise Value (EV)")
    st.subheader(f"${current_ev/1e9:,.2f} B")
    st.caption("Market Cap + Total Debt + Preferred Stock - Total Cash")
with col_res:
    st.write("BTC Reserve Value")
    st.subheader(f"${current_btc_res/1e9:,.2f} B")
    st.caption(f"Based on {mstr_btc_holdings:,.0f} BTC")

# ================= 6. Chart Area =================

if hist_ok and not m_hist.empty:
    df = pd.merge(m_hist, b_hist, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()
    
    # Historical Calculations
    h_mcap = df['Price_MSTR'] * shares
    h_ev = h_mcap + debt + pref - cash
    h_res = df['Price_BTC'] * mstr_btc_holdings
    
    df['mNAV'] = h_ev / h_res
    df['NAV'] = h_res / shares 
    df['P_D_Percent'] = (df['mNAV'] - 1)
    df['BTC_per_Share'] = mstr_btc_holdings / shares
    df['Net_Leverage'] = debt / (h_mcap + debt)
    df['MSTR_BTC_Ratio'] = df['Price_MSTR'] / df['Price_BTC']

    if selected_metrics:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for label, col in selected_metrics:
            # Secondary Y axis for percentage/multiple metrics
            is_sec = col in ["mNAV", "P_D_Percent", "Net_Leverage", "MSTR_BTC_Ratio"]
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label, line=dict(width=2.5)), secondary_y=is_sec)
        
        fig.update_layout(
            template="plotly_dark", hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # Formatting for Percentage Scales
        if any(m[1] in ["P_D_Percent", "Net_Leverage"] for m in selected_metrics):
            fig.update_yaxes(tickformat=".1%", secondary_y=True)
            
        st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ Historical trend data failed to load")
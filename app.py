import streamlit as st
import yfinance as yf
from twelvedata import TDClient
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import google.generativeai as genai
from datetime import datetime
import pytz

# ================= 1. 頁面設定 (Page Config) =================
st.set_page_config(page_title="MSTR財務指標監測", layout="wide")
st.title("MSTR (MicroStrategy) 財務指標監測")

# --- 安全配置 ---
try:
    TWELVE_DATA_KEY = st.secrets["TWELVE_DATA_KEY"]
except:
    st.error("❌ 未偵測到 API 金鑰，請在 Secrets 中設定 TWELVE_DATA_KEY")
    st.stop()
    
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
except:
    st.error("❌ 未偵測到 API 金鑰，請在 Secrets 中設定 GEMINI_API_KEY")
    st.stop()
    
def generate_mstr_summary(data_snapshot):
    """
    接收當前數據並產生 AI 摘要
    """
    # 修正模型名稱為清單中的正確路徑
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    prompt = f"""
    你是一位專業的 DAT (Digital Asset Treasury) 財務分析師。
    請根據以下 MSTR (MicroStrategy) 的即時監測數據進行簡短解讀：
    
    - 當前 BTC 價格: ${data_snapshot['btc_price']:,}
    - MSTR 溢價率 (Premium): {data_snapshot['premium']:.1%}
    - 當前 mNAV 倍數: {data_snapshot['mnav']:.2f}x
    - 累計 BTC Yield: {data_snapshot['yield']:.2%}
    - 淨槓桿率 (Net Leverage): {data_snapshot['leverage']:.1%}
    
    請提供以下內容（使用繁體中文）：
    1. 【現狀解讀】：一句話總結當前財務狀態。
    2. 【趨勢與風險】：分析溢價率與槓桿率是否處於健康區間。
    3. 【關鍵觀察點】：提醒投資者接下來該注意哪個數據。
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 摘要生成失敗：{str(e)}"

# ================= 2. 數據抓取 (Data Fetching) =================

@st.cache_data(ttl=3600)
def get_mstr_holdings():
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
    except: st.sidebar.warning("⚠️ BTC 即時報價連線失敗")
    try:
        m_p = yf.Ticker("MSTR").fast_info['last_price']
    except: st.sidebar.warning("⚠️ MSTR 即時報價連線失敗")
    return m_p, b_p

# ================= 3. 數據初始化 =================

shares, debt, pref, cash, fund_ok = get_mstr_fundamentals()
mstr_btc_holdings, btc_ok = get_mstr_holdings()

# 初始化 AI 分析結果的 Session State (防止重新整理消失)
if "analysis_res" not in st.session_state:
    st.session_state.analysis_res = None

# ================= 4. 側邊欄 (Sidebar) =================

with st.sidebar:
    st.header("基準參數")
    st.write(f"持倉 (Holdings): **{mstr_btc_holdings:,.0f} BTC**")
    st.write(f"股數 (Shares): **{shares/1e6:.1f} M**")
    st.write(f"總債務 (Debt): **${debt/1e9:.2f} B**")
    st.write(f"優先股 (Pref): **${pref/1e9:.2f} B**")
    st.write(f"現金 (Cash): **${cash/1e9:.2f} B**")
    
    if st.button("🔄 強制刷新數據 (Refresh)"):
        st.cache_data.clear()
        st.session_state.analysis_res = None
        st.rerun()
        
    st.divider()
    st.subheader("圖表指標")
    selected_metrics = []
    options = {
        "MSTR 股價 (MSTR Price)": "Price_MSTR", 
        "mNAV 倍數 (mNAV Multiple)": "mNAV", 
        "溢價率 (Premium %)": "P_D_Percent",
        "收益率 (BTC Yield)": "Yield_Series",
        "淨槓桿率 (Net Leverage)": "Leverage_Series"
    }
    for label, col in options.items():
        is_default = col in ["mNAV"]
        if st.checkbox(label, value=is_default, key=f"chk_{col}"):
            selected_metrics.append((label, col))

# ================= 5. 核心計算 (Core Calculations) =================

rt_m, rt_b = get_realtime_data()
m_hist, b_hist, hist_ok = load_historical_data(TWELVE_DATA_KEY)

cur_m = rt_m if rt_m else (m_hist.iloc[-1] if not m_hist.empty else 1800.0)
cur_b = rt_b if rt_b else (b_hist.iloc[-1] if not b_hist.empty else 65000.0)

current_mcap = cur_m * shares
current_ev = current_mcap + debt + pref - cash
current_btc_res = cur_b * mstr_btc_holdings
current_mnav = current_ev / current_btc_res if current_btc_res > 0 else 1.0

cur_bps = mstr_btc_holdings / shares
initial_bps = mstr_btc_holdings / (shares * 0.95) 
real_yield = (cur_bps / initial_bps) - 1
cur_leverage = (debt - cash) / current_ev if current_ev > 0 else 0.0

# --- 儀表板 ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC 幣價 (Price)", f"${cur_b:,.0f}")
c2.metric("MSTR 股價 (Price)", f"${cur_m:,.2f}")
c3.metric("mNAV 倍數 (Multiple)", f"{current_mnav:.2f}x")
c4.metric("溢價率 (Premium %)", f"{(current_mnav-1)*100:.1f}%")

c5, c6, c7, c8 = st.columns(4)
c5.metric("每千股含幣 (BPTS)", f"{cur_bps*1000:.6f}")
c6.metric("強度比 (MSTR/BTC)", f"{cur_m/cur_b:.4f}")
c7.metric("BTC 收益率 (Yield)", f"{real_yield:.2%}")
c8.metric("淨槓桿率 (Net Leverage)", f"{cur_leverage:.1%}")

st.caption("數據來源：Twelve Data, Yahoo Finance, CoinGecko Public Treasury API")
st.caption("免責聲明：本儀表板僅供財務指標監測與學術研究參考，不構成任何投資建議。加密資產具備高風險，請審慎評估。")
# 1. 設定目標時區
local_tz = pytz.timezone('Asia/Taipei')

# 2. 取得當前 UTC 時間並轉換為本地時間
# 這樣不論伺服器在美國還是歐洲，顯示的都會是台灣時間
local_time = datetime.now(pytz.utc).astimezone(local_tz)

# 3. 格式化輸出
formatted_time = local_time.strftime('%Y-%m-%d %H:%M:%S')

st.caption(f"🕒 最後更新時間：{formatted_time} (UTC+8)")

st.markdown("---")

# ================= 6. 圖表區與 AI 分析 =================

if hist_ok and not m_hist.empty:
    df = pd.merge(m_hist, b_hist, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()
    
    h_mcap = df['Price_MSTR'] * shares
    h_ev = h_mcap + debt + pref - cash
    h_res = df['Price_BTC'] * mstr_btc_holdings
    df['mNAV'] = h_ev / h_res
    df['P_D_Percent'] = (df['mNAV'] - 1)
    df['Yield_Series'] = real_yield * (df.reset_index().index / len(df))
    df['Leverage_Series'] = (debt - cash) / h_ev
    
    st.markdown("""
        <style>
        .plot-container {
            border: 1px solid #333333; /* 邊框顏色 */
            border-radius: 15px;      /* 圓角弧度 */
            overflow: hidden;         # 確保內容不會超出圓角
            box-shadow: 0 4px 15px rgba(0,0,0,0.3); /* 淡淡的陰影 */
            padding: 10px;            /* 給圖表一點呼吸空間 */
            background-color: rgba(10,10,10,1); /* 背景色 */
        }
        </style>
    """, unsafe_allow_html=True)

    # 2. 將圖表放入這個容器中
    with st.container():
        st.markdown('<div class="plot-container">', unsafe_allow_html=True)
        
        if selected_metrics:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            has_negative = False
            for label, col in selected_metrics:
                is_sec = col in ["mNAV", "P_D_Percent", "Yield_Series", "Leverage_Series"]
                fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label, line=dict(width=2.5)), secondary_y=is_sec)
                if col in ["P_D_Percent", "Leverage_Series"]: has_negative = True
            
            if any(m[1] in ["P_D_Percent", "Yield_Series", "Leverage_Series"] for m in selected_metrics):
                fig.update_yaxes(tickformat=".1%", secondary_y=True)
                
            if has_negative:
                fig.add_hline(y=0, line_dash="dash", line_color="grey", line_width=1.5, secondary_y=True)
                
            st.plotly_chart(fig, width='stretch')
            
            # --- AI 分析按鈕 (修正機制) ---
            if st.button("產生 AI 分析與趨勢解讀"):
                with st.spinner("正在呼叫 Gemini 2.5 分析數據..."):
                    snapshot = {
                        "btc_price": cur_b,
                        "premium": (current_mnav - 1),
                        "mnav": current_mnav,
                        "yield": real_yield,
                        "leverage": cur_leverage
                    }
                    st.session_state.analysis_res = generate_mstr_summary(snapshot)
            
            # 顯示 AI 分析結果 (確保不會因為重新整理而消失)
            if st.session_state.analysis_res:
                st.info("AI 分析與趨勢解讀")
                st.markdown(st.session_state.analysis_res)
                if st.button("清除 AI 內容"):
                    st.session_state.analysis_res = None
                    st.rerun()
        # 注意：圖表的 paper_bgcolor 最好設為透明 "rgba(0,0,0,0)" 
        # 這樣圓角背景才會由 CSS 控制
        fig.update_layout(template="plotly_dark", hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",margin=dict(l=40, r=40, t=50, b=50),showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))

else:
    st.warning("⚠️ 歷史趨勢載入失敗")
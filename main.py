import streamlit as st
from twelvedata import TDClient
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 1. 初始化與頁面設定 =================
st.set_page_config(page_title="DAT.co 監測站", layout="wide")

st.title("📊 DAT.co (Digital Asset Treasury) 財務指標監測")
st.write("本站即時監控 MicroStrategy (MSTR) 的比特幣本位財務表現。")

# --- API 配置 ---
TWELVE_DATA_KEY = "42d2074881da4044b2c7dc363208af13"

# ================= 2. 核心數據抓取函數 =================

@st.cache_data(ttl=3600)
def get_mstr_holdings():
    """獲取 MSTR 最新比特幣持倉量"""
    url = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = response.json()
        for co in data.get('companies', []):
            if "Strategy" in co.get('name', ''):
                return float(co.get('total_holdings', 0))
    except:
        pass
    return 766970.0  # 2026/04 預設保險值

@st.cache_data(ttl=3600)
def get_mstr_shares(api_key):
    """獲取 MSTR 最新發行總股數"""
    url = f"https://api.twelvedata.com/quote?symbol=MSTR&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        # 嘗試從統計數據中獲取流通股數
        shares = data.get('shares_outstanding') or data.get('statistics', {}).get('shares_outstanding')
        if shares:
            return float(shares)
    except:
        pass
    return 380000000.0  # 2026/04 預設保險值 (約 3.8 億股)

@st.cache_data(ttl=8)
def load_market_data(api_key):
    """獲取 MSTR 與 BTC 歷史收盤價"""
    td = TDClient(apikey=api_key)
    mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
    btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
    
    # 統一欄位名稱
    mstr_ts.columns = [c.lower() for c in mstr_ts.columns]
    btc_ts.columns = [c.lower() for c in btc_ts.columns]
    
    return mstr_ts['close'], btc_ts['close']

# ================= 3. 數據處理流 =================

# A. 獲取基本參數
mstr_btc_holdings = get_mstr_holdings()
total_shares = get_mstr_shares(TWELVE_DATA_KEY)

# B. 抓取價格並合併
try:
    mstr_close, btc_close = load_market_data(TWELVE_DATA_KEY)
    df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()

    # C. 計算衍生指標 (所有繪圖所需的 Key 都在這裡產生)
    # 1. 每股含幣量
    df['BTC_per_Share'] = mstr_btc_holdings / total_shares
    # 2. 估計 NAV
    df['NAV'] = df['Price_BTC'] * df['BTC_per_Share']
    # 3. mNAV 倍數
    df['mNAV'] = df['Price_MSTR'] / df['NAV']
    # 4. 溢價/折價率
    df['P_D_Percent'] = ((df['Price_MSTR'] - df['NAV']) / df['NAV'])

except Exception as e:
    st.error(f"數據加載失敗，請檢查 API Key: {e}")
    df = pd.DataFrame()

# ================= 4. UI 側邊欄控制 =================

st.sidebar.header("控制面板")
st.sidebar.metric("監測持倉 (BTC)", f"{mstr_btc_holdings:,.0f}")
st.sidebar.metric("流通股數 (Shares)", f"{total_shares/1e6:.1f}M")

selected_metrics = []
with st.sidebar.expander("指標顯示切換", expanded=True):
    options = {
        "MSTR 股價": "Price_MSTR",
        "估計 NAV": "NAV",
        "mNAV 倍數": "mNAV",
        "溢價/折價率 (%)": "P_D_Percent"
    }
    for i, (label, col_name) in enumerate(options.items()):
        # 使用唯一 Key 防止重複 ID 錯誤
        if st.checkbox(label, value=(i in [0, 1]), key=f"chk_{i}"):
            selected_metrics.append((label, col_name))

# ================= 5. 專業繪圖函數 =================

def plot_professional_chart(df, selected_metrics):
    if not selected_metrics or df.empty:
        st.info("請在側邊欄勾選指標以開始分析。")
        return

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    for label, col in selected_metrics:
        # 決定軸位：價格類放左邊，比例類放右邊
        is_secondary = col in ["mNAV", "P_D_Percent"]
        
        fig.add_trace(
            go.Scatter(
                x=df.index, 
                y=df[col], 
                name=label,
                mode='lines',
                line=dict(width=2.5)
            ),
            secondary_y=is_secondary
        )

    # 裝飾：如果選了溢價率，增加 0% 水平線
    if "P_D_Percent" in [m[1] for m in selected_metrics]:
        fig.add_hline(y=0, line_dash="dash", line_color="gray", secondary_y=True)

    # 佈局設定
    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        height=600,
        xaxis=dict(range=[df.index.min(), df.index.max()], fixedrange=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    # 軸標題與鎖定 (防止 Y 軸被縮放搞亂)
    fig.update_yaxes(title_text="Price (USD)", secondary_y=False, fixedrange=True)
    fig.update_yaxes(title_text="Ratio / %", secondary_y=True, fixedrange=True)

    # 互動限制：只能框選放大，不能滾輪縮小
    config = {
        'scrollZoom': False,
        'modeBarButtonsToRemove': ['zoomOut2d', 'autoScale2d', 'resetScale2d', 'pan2d'],
        'displaylogo': False
    }

    st.plotly_chart(fig, use_container_width=True, config=config)

# ================= 6. 主畫面顯示 =================

if not df.empty:
    # 頂部指標卡
    c1, c2, c3, c4 = st.columns(4)
    latest = df.iloc[-1]
    c1.metric("BTC 價格", f"${latest['Price_BTC']:,.0f}")
    c2.metric("MSTR 股價", f"${latest['Price_MSTR']:,.2f}")
    c3.metric("當前 mNAV", f"{latest['mNAV']:.2f}x")
    c4.metric("溢價/折價", f"{latest['P_D_Percent']:.1f}%")

    # 繪製圖表
    plot_professional_chart(df, selected_metrics)
    
    # 數據表摘要
    with st.expander("查看原始數據表"):
        st.dataframe(df.style.format("{:,.2f}"))
else:
    st.warning("無法獲取市場數據，請確認網路連線或 Twelve Data API 額度。")
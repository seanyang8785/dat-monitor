import streamlit as st
from twelvedata import TDClient
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

# ================= 1. 初始化與頁面設定 =================
st.set_page_config(page_title="DAT.co 監測站", layout="wide")

st.title("📊 DAT.co (Digital Asset Treasury) 財務指標監測")
st.write("本站監測 MicroStrategy (MSTR) 的各項指標及其與比特幣的關係。")

# --- 定義常數 ---
# 根據 2026 年初數據，MSTR 總股數約為 2.2 億股 (請依實際情況微調)
TOTAL_SHARES = 220000000 

# ================= 2. 數據獲取函數 =================

@st.cache_data(ttl=3600)
def get_mstr_holdings():
    """從 CoinGecko API 獲取最新的 MSTR 持幣量"""
    url = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        companies = data.get('companies', [])
        for co in companies:
            if "Strategy" in co.get('name', ''):
                return float(co.get('total_holdings', 0))
    except Exception as e:
        st.sidebar.error(f"API 抓取失敗: {e}")
    # 預設保險值
    return 252220.0

@st.cache_data(ttl=600)
def load_market_data(api_key):
    """從 Twelve Data 獲取股價與幣價"""
    td = TDClient(apikey=api_key)
    # 抓取 100 天數據
    mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
    btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
    
    # 統一處理欄位名稱 (轉小寫)
    mstr_ts.columns = [c.lower() for c in mstr_ts.columns]
    btc_ts.columns = [c.lower() for c in btc_ts.columns]
    
    return mstr_ts['close'], btc_ts['close']

# ================= 3. 執行數據處理流 =================

# A. 獲取持倉量
mstr_btc_holdings = get_mstr_holdings()

# B. 獲取市場價格
try:
    mstr_close, btc_close = load_market_data("42d2074881da4044b2c7dc363208af13")
    
    # C. 合併並對齊日期
    df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
    df.columns = ['Price_MSTR', 'Price_BTC']
    df = df.sort_index()

    # D. [核心] 計算衍生指標 - 必須在勾選單之前完成
    df['NAV'] = (df['Price_BTC'] * mstr_btc_holdings) / TOTAL_SHARES
    df['mNAV'] = df['Price_MSTR'] / df['NAV']
    df['P_D_Percent'] = ((df['Price_MSTR'] - df['NAV']) / df['NAV'])

except Exception as e:
    st.error(f"數據處理發生錯誤: {e}")
    df = pd.DataFrame()

# ================= 4. UI 控制面板 (側邊欄) =================

st.sidebar.header("控制面板")
st.sidebar.info(f"目前監測持倉：{mstr_btc_holdings:,.0f} BTC")

selected_metrics = []
with st.sidebar.expander("📈 選擇顯示指標", expanded=True):
    # 標籤與 DataFrame 欄位的對應關係
    options = {
        "MSTR 股價": "Price_MSTR",
        "估計 NAV": "NAV",
        "mNAV 倍數": "mNAV",
        "溢價/折價率 (%)": "P_D_Percent"
    }
    
    for i, (label, col_name) in enumerate(options.items()):
        # 加入唯一的 key 以防止 DuplicateElementId 錯誤
        if st.checkbox(label, value=(i == 0), key=f"metric_check_{i}"):
            selected_metrics.append((label, col_name))

# ================= 5. 繪圖與顯示邏輯 =================

def plot_mstr_chart(df, selected_metrics):
    if not selected_metrics or df.empty:
        st.info("請在側邊欄勾選指標或檢查 API 狀態。")
        return

    # 建立支援雙 Y 軸的圖表
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    for label, col in selected_metrics:
        # 判斷是否放在右側 Y 軸 (比例與百分比)
        is_secondary = col in ["mNAV", "P_D_Percent"]
        
        fig.add_trace(
            go.Scatter(
                x=df.index, 
                y=df[col], 
                name=label,
                mode='lines',
                line=dict(width=2)
            ),
            secondary_y=is_secondary
        )
    
    # 加上 0% 基準線 (如果選了溢價率)
    if any(m[1] == "P_D_Percent" for m in selected_metrics):
        fig.add_hline(y=0, line_dash="dash", line_color="gray", secondary_y=True)

    # 佈局美化
    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        xaxis=dict(
            range=[df.index.min(), df.index.max()],
            fixedrange=False # 允許放大
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    # 座標軸鎖定設定
    fig.update_yaxes(title_text="價格 (USD)", secondary_y=False, fixedrange=True)
    fig.update_yaxes(title_text="倍數 / 百分比", secondary_y=True, fixedrange=True)

    # 限制縮放功能
    config = {
        'scrollZoom': False, # 禁止滾輪縮小
        'modeBarButtonsToRemove': ['zoomOut2d', 'autoScale2d', 'resetScale2d', 'pan2d'],
        'displaylogo': False
    }

    st.plotly_chart(fig, use_container_width=True, config=config)

# --- 主畫面呈現 ---
if not df.empty:
    # 顯示圖表
    plot_mstr_chart(df, selected_metrics)

    # 顯示關鍵指標卡片
    c1, c2, c3 = st.columns(3)
    c1.metric("最新股價", f"${df['Price_MSTR'].iloc[-1]:,.2f}")
    c2.metric("最新 mNAV", f"{df['mNAV'].iloc[-1]:.2f}x")
    c3.metric("溢價/折價", f"{df['P_D_Percent'].iloc[-1]:.1f}%")
else:
    st.warning("等待數據加載中...")
import streamlit as st
import yfinance as yf
import pandas as pd

# 設置網頁標題
st.set_page_config(page_title="DAT.co 監測站", layout="wide")

st.title("📊 DAT.co (Digital Asset Treasury) 財務指標監測")
st.write("本站監測 MicroStrategy (MSTR) 的 mNAV 指標及其與比特幣的關係。")

# 1. 定義數據 (以 MSTR 為例)
ticker_symbol = "MSTR"
btc_symbol = "BTC-USD"
mstr_btc_holdings = 252220  # 截至最新數據的持有量，可根據報表更新

# 2. 抓取數據 (過去一年)
@st.cache_data
def load_data():
    mstr = yf.download(ticker_symbol, period="1y")
    btc = yf.download(btc_symbol, period="1y")
    return mstr, btc

mstr_data, btc_data = load_data()

# 3. 處理數據並計算 mNAV
# 確保我們只取 'Close' 這一欄，並處理 yfinance 可能回傳的格式
mstr_close = mstr_data['Close'].dropna()
btc_close = btc_data['Close'].dropna()

# 建立對齊日期的 DataFrame
df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
df.columns = ['Price_MSTR', 'Price_BTC'] # 強制重新命名

# --- 重要：防錯檢查 ---
if df.empty:
    st.error("❌ 抓取不到重合的日期數據，請檢查網絡連線或稍後再試。")
else:
    # 4. 計算指標
    total_shares = 197000000 
    mstr_btc_holdings = 252220

    df['Market_Cap'] = df['Price_MSTR'] * total_shares
    df['BTC_Value_Held'] = df['Price_BTC'] * mstr_btc_holdings
    df['mNAV'] = df['Market_Cap'] / df['BTC_Value_Held']

    # 5. UI 顯示
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("價格走勢比較")
        st.line_chart(df[['Price_MSTR', 'Price_BTC']])

    with col2:
        st.subheader("mNAV 溢價倍數")
        st.area_chart(df['mNAV'])
        # 使用 iloc 之前先確認真的有資料
        latest_mnav = df['mNAV'].iloc[-1]
        st.write(f"當前最新 mNAV: **{latest_mnav:.2f}**")

    # 顯示數據表供除錯 (可選)
    with st.expander("查看原始數據"):
        st.write(df.tail())
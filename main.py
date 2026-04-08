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

# 3. 計算 mNAV 指標
# mNAV = 市值 / (BTC 持有量 * BTC 價格)
# 簡化計算：(股價 * 流通股數) / (持有量 * BTC 價格)
# 這裡我們直接用 (MSTR 收盤價 / 每股含幣量) 的比例來觀察溢價
mstr_close = mstr_data['Close']
btc_close = btc_data['Close']

# 為了對齊日期，進行合併
df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, suffixes=('_MSTR', '_BTC'))

# 假設 MSTR 總股數約為 1.97 億股 (2024數據，請依實際情況調整)
total_shares = 197000000 
df['Market_Cap'] = df['Close_MSTR'] * total_shares
df['BTC_Value_Held'] = df['Close_BTC'] * mstr_btc_holdings
df['mNAV'] = df['Market_Cap'] / df['BTC_Value_Held']

# 4. 網頁 UI 佈局
col1, col2 = st.columns(2)

with col1:
    st.subheader("MSTR 股價 vs 比特幣走勢")
    st.line_chart(df[['Close_MSTR', 'Close_BTC']])

with col2:
    st.subheader("mNAV 溢價倍數 (Premium/Discount)")
    st.area_chart(df['mNAV'])
    st.write(f"當前最新 mNAV: **{df['mNAV'].iloc[-1]:.2f}**")

st.info("💡 解讀：當 mNAV > 1.0，代表市場給予該公司比特幣持倉溢價；反之則為折價。")
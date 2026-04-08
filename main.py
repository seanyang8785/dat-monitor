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
# 確保我們只取 'Close' 這一欄，並處理可能的 Multi-Index 格式
mstr_close = mstr_data['Close'].dropna()
btc_close = btc_data['Close'].dropna()

# 建立一個新的 DataFrame 來對齊日期
df = pd.DataFrame(index=mstr_close.index)
df['Price_MSTR'] = mstr_close
df['Price_BTC'] = btc_close

# 移除任何有缺失值的日期（例如假日股市休市但加密貨幣沒關）
df = df.dropna()

# 4. 計算指標
total_shares = 197000000 
mstr_btc_holdings = 252220

df['Market_Cap'] = df['Price_MSTR'] * total_shares
df['BTC_Value_Held'] = df['Price_BTC'] * mstr_btc_holdings
df['mNAV'] = df['Market_Cap'] / df['BTC_Value_Held']

# 5. UI 顯示 (對應新的欄位名稱)
col1, col2 = st.columns(2)
with col1:
    st.subheader("價格走勢比較")
    # 使用標準化或雙軸，這裡我們先簡單顯示
    st.line_chart(df[['Price_MSTR', 'Price_BTC']])

with col2:
    st.subheader("mNAV 溢價倍數")
    st.area_chart(df['mNAV'])
    st.write(f"當前最新 mNAV: **{df['mNAV'].iloc[-1]:.2f}**")
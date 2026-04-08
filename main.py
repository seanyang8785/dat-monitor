import streamlit as st
from twelvedata import TDClient
import pandas as pd
import requests

# 設置網頁標題
st.set_page_config(page_title="DAT.co 監測站", layout="wide")

st.title("📊 DAT.co (Digital Asset Treasury) 財務指標監測")
st.write("本站監測 MicroStrategy (MSTR) 的 mNAV 指標及其與比特幣的關係。")

def scrape_mstr_holdings():
    url = "https://bitcointreasuries.net/"
    
    # 偽裝成一般的 Chrome 瀏覽器
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        # 如果狀態碼不是 200，會直接噴錯進入 except
        response.raise_for_status() 
        
        # 使用抓下來的 HTML 文本給 Pandas 解析
        tables = pd.read_html(response.text)
        df = tables[0]
        
        # 尋找 MicroStrategy (這段邏輯維持不變)
        mstr_row = df[df.iloc[:, 0].str.contains("MicroStrategy", na=False)]
        holdings_str = str(mstr_row.iloc[0, 2])
        holdings = float(holdings_str.replace(',', '').replace(' BTC', ''))
        return holdings
        
    except Exception as e:
        st.error(f"自動抓取失敗：{e}")
        # 萬一失敗，回傳一個寫死的數值，保證 App 不會當機
        return 252220

# 1. 定義數據 (以 MSTR 為例)
ticker_symbol = "MSTR"
btc_symbol = "BTC-USD"
mstr_btc_holdings = scrape_mstr_holdings()  # 截至最新數據的持有量，可根據報表更新

# 2. 抓取數據 (過去一年)
td = TDClient(apikey="42d2074881da4044b2c7dc363208af13")
@st.cache_data
def load_data():
    # 抓取 MSTR 股價
    mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
    # 抓取 BTC 價格
    btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
    
    return mstr_ts, btc_ts

mstr_data, btc_data = load_data()

@st.cache_data
def load_data():
    # 抓取 MSTR (美股)
    # Twelve Data 的欄位名稱預設通常是小寫 'close'
    mstr_ts = td.time_series(symbol="MSTR", interval="1day", outputsize=100).as_pandas()
    # 抓取 BTC (加密貨幣)
    btc_ts = td.time_series(symbol="BTC/USD", interval="1day", outputsize=100).as_pandas()
    return mstr_ts, btc_ts

mstr_raw, btc_raw = load_data()

# 3. 處理資料 (解決 KeyError 的核心)
# 強制將所有欄位名稱轉為小寫，並取出 'close'
mstr_raw.columns = [c.lower() for c in mstr_raw.columns]
btc_raw.columns = [c.lower() for c in btc_raw.columns]

# Twelve Data 回傳的 Index 通常是時間，我們直接取 'close'
mstr_close = mstr_raw['close']
btc_close = btc_raw['close']

# 4. 合併與對齊
df = pd.merge(mstr_close, btc_close, left_index=True, right_index=True, how='inner')
df.columns = ['Price_MSTR', 'Price_BTC']
df = df.sort_index() # 確保時間是由舊到新

# --- 防錯檢查 ---
if df.empty:
    st.error("目前抓不到重合的日期數據，請確認 API Key 是否正確或剩餘次數。")
else:
    # 4. 計算 mNAV
    total_shares = 197000000 
    mstr_btc_holdings = 252220

    df['Market_Cap'] = df['Price_MSTR'] * total_shares
    df['BTC_Value_Held'] = df['Price_BTC'] * mstr_btc_holdings
    df['mNAV'] = df['Market_Cap'] / df['BTC_Value_Held']

    # 5. UI 顯示
    st.line_chart(df[['Price_MSTR', 'Price_BTC']])
    st.area_chart(df['mNAV'])
    st.metric("最新 mNAV 溢價倍數", f"{df['mNAV'].iloc[-1]:.2f}")
import streamlit as st
from twelvedata import TDClient
import pandas as pd
import requests

# 設置網頁標題
st.set_page_config(page_title="DAT.co 監測站", layout="wide")

st.title("📊 DAT.co (Digital Asset Treasury) 財務指標監測")
st.write("本站監測 MicroStrategy (MSTR) 的 mNAV 指標及其與比特幣的關係。")

@st.cache_data(ttl=60)  # 每小時更新一次持倉數據即可，不用太頻繁
def get_mstr_holdings():
    # CoinGecko 的上市公司持幣量接口
    url = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
    headers = {"User-Agent": "Mozilla/5.0"} # 加入簡單標頭避免被阻擋
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # 從 companies 列表裡尋找 MicroStrategy
        companies = data.get('companies', [])
        for co in companies:
            # 使用更保險的名稱檢查
            if "MicroStrategy" in co.get('name', ''):
                return float(co.get('total_holdings', 0))
                
    except Exception as e:
        # 如果 API 失敗，在畫面上顯示一個小警告，但維持運作
        st.sidebar.warning(f"API 抓取失敗，使用預設持倉量。錯誤原因: {e}")
        
    # 萬一 API 壞掉或沒抓到，回傳最新的已知數值 (2026/04 數據約為 252220)
    return 766970

# 1. 定義數據 (以 MSTR 為例)
ticker_symbol = "MSTR"
btc_symbol = "BTC-USD"
mstr_btc_holdings = get_mstr_holdings()  # 截至最新數據的持有量，可根據報表更新
st.sidebar.info(f"目前監測持倉：{mstr_btc_holdings:,.0f} BTC")

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
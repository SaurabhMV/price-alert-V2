import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd
import numpy as np

# --- Page Config ---
st.set_page_config(page_title="Trend Strength Bot", page_icon="💪", layout="wide")
st.title("💪 Pro Bot: Trend Strength & Pullback Analyzer")

# --- Sidebar ---
st.sidebar.header("Strategy Settings")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
chat_id = st.sidebar.text_input("Chat ID")
ticker_input = st.sidebar.text_input("Watchlist", value="NVDA, TSLA, AAPL, BTC-USD")
adx_threshold = st.sidebar.slider("Min Trend Strength (ADX)", 15, 50, 25)

# --- Technical Indicators ---
def calculate_adx(df, period=14):
    """Calculates ADX (Trend Strength) using pure Pandas"""
    df = df.copy()
    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = abs(df['High'] - df['Close'].shift(1))
    df['L-C'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-C', 'L-C']].max(axis=1)
    
    df['UpMove'] = df['High'] - df['High'].shift(1)
    df['DownMove'] = df['Low'].shift(1) - df['Low']
    
    df['+DM'] = np.where((df['UpMove'] > df['DownMove']) & (df['UpMove'] > 0), df['UpMove'], 0)
    df['-DM'] = np.where((df['DownMove'] > df['UpMove']) & (df['DownMove'] > 0), df['DownMove'], 0)
    
    # Smooth with Rolling Average
    df['+DI'] = 100 * (df['+DM'].rolling(window=period).mean() / df['TR'].rolling(window=period).mean())
    df['-DI'] = 100 * (df['-DM'].rolling(window=period).mean() / df['TR'].rolling(window=period).mean())
    df['DX'] = 100 * abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'])
    
    return df['DX'].rolling(window=period).mean()

def fetch_trend_data(tickers):
    results = []
    for symbol in tickers:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period='60d', interval='1h')
            if hist.empty: continue
            
            # 1. Standard Calculations
            curr = hist['Close'].iloc[-1]
            h3 = hist['High'].tail(72).max() 
            pullback = ((curr - h3) / h3) * 100
            
            # 2. ADX (Trend Strength)
            hist['ADX'] = calculate_adx(hist)
            curr_adx = hist['ADX'].iloc[-1]
            
            # 3. Pullback Severity (Comparison to History)
            # Calculate all hourly % drops in the last 60 days to find the "Average Drop"
            hist['Hourly_Change'] = hist['Close'].pct_change() * 100
            avg_drop = hist[hist['Hourly_Change'] < 0]['Hourly_Change'].mean() # e.g., -0.8%
            
            # Is current drop unusual? (e.g., current is -5%, avg is -1%)
            severity_ratio = pullback / (avg_drop * 10) # rough scaler
            
            # Trend Interpretation
            trend_status = "😴 Weak/Choppy"
            if curr_adx > 25: trend_status = "🔥 Strong Trend"
            if curr_adx > 50: trend_status = "🚀 Super Trend"

            results.append({
                "Ticker": symbol, 
                "Price": curr, 
                "Pullback": pullback,
                "ADX": curr_adx,
                "Status": trend_status,
                "Avg_Drop": avg_drop
            })
        except: continue
    return results

def send_alert(msg):
    if bot_token and chat_id:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", 
                      json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

# --- Main App ---
if st.button("Analyze Trends"):
    st.write("Fetching data... (This uses ADX formula)")
    data = fetch_trend_data([t.strip() for t in ticker_input.split(",")])
    
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)
    
    for i in data:
        # ALERT LOGIC: Strong Trend (ADX>25) + Significant Pullback
        if i['ADX'] > adx_threshold and i['Pullback'] < -3.0:
            msg = f"💪 *TREND STRENGTH ALERT: {i['Ticker']}*\n"
            msg += f"The stock is in a **{i['Status']}** (ADX: {i['ADX']:.1f})\n"
            msg += f"📉 Current Pullback: `{i['Pullback']:.2f}%`\n"
            msg += f"📊 Historical Avg Drop: `{i['Avg_Drop']:.2f}%`\n"
            msg += "This is a strong trend taking a breather. Watch for entry!"
            send_alert(msg)
            st.success(f"Alert sent for {i['Ticker']}")

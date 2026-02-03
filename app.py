import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd
import numpy as np

# --- Page Config ---
st.set_page_config(page_title="AI Confluence Trader", page_icon="🎯", layout="wide")
st.title("🎯 AI Confluence Trader: Live Dashboard")

# --- Sidebar: Configuration & Control ---
st.sidebar.header("🔐 Credentials")
try:
    bot_token = st.secrets["BOT_TOKEN"]
    chat_id = st.secrets["CHAT_ID"]
    st.sidebar.success("✅ Secrets Loaded")
except:
    bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
    chat_id = st.sidebar.text_input("Authorized Chat ID")

st.sidebar.header("⚙️ Strategy Settings")
ticker_input = st.sidebar.text_input("Watchlist", value="AMZN, AVGO, GOOGL, JPM, META.TO, MU, NVDA.TO, QCOM, SHOP.TO, TD.TO, MSFT, SVR.TO, ZGLD.TO")
check_interval = st.sidebar.number_input("Refresh Rate (sec)", min_value=10, value=60)

st.sidebar.header("🚀 Bot Control")
if 'running' not in st.session_state: st.session_state.running = False

col1, col2 = st.sidebar.columns(2)
if col1.button("▶️ START BOT", use_container_width=True): st.session_state.running = True
if col2.button("🛑 STOP BOT", use_container_width=True): st.session_state.running = False

# --- Indicator Calculations ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_adx(df, period=14):
    df = df.copy()
    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = abs(df['High'] - df['Close'].shift(1))
    df['L-C'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-C', 'L-C']].max(axis=1)
    df['Up'] = df['High'] - df['High'].shift(1)
    df['Down'] = df['Low'].shift(1) - df['Low']
    df['+DM'] = np.where((df['Up'] > df['Down']) & (df['Up'] > 0), df['Up'], 0)
    df['-DM'] = np.where((df['Down'] > df['Up']) & (df['Down'] > 0), df['Down'], 0)
    df['+DI'] = 100 * (df['+DM'].rolling(window=period).mean() / df['TR'].rolling(window=period).mean())
    df['-DI'] = 100 * (df['-DM'].rolling(window=period).mean() / df['TR'].rolling(window=period).mean())
    df['DX'] = 100 * abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'])
    return df['DX'].rolling(window=period).mean()

# --- Scoring & Recommendation Logic ---
def get_analysis(rsi, adx, dist_sma):
    score = 0
    if rsi < 30: score += 4
    elif rsi < 40: score += 2
    if adx > 25: score += 3
    elif adx > 20: score += 1
    if -2 < dist_sma < 2: score += 3 
    elif dist_sma > 0: score += 1     

    rec = "HOLD"
    reason = "Neutral"
    if adx > 20 and dist_sma > -2 and rsi < 40:
        rec = "BUY"; reason = "Bullish Pullback"
    elif rsi < 30 and dist_sma < -5:
        rec = "BUY (RISKY)"; reason = "Oversold Bounce"
    if rsi > 70:
        rec = "SELL"; reason = "Overbought"
    elif adx > 25 and dist_sma < -2:
        rec = "SELL / AVOID"; reason = "Strong Downtrend"
    
    return score, rec, reason

# --- Data Engine ---
def fetch_data(tickers):
    results = []
    for symbol in tickers:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period='60d', interval='1h')
            if hist.empty: continue
            
            curr = hist['Close'].iloc[-1]
            h3 = hist['High'].tail(72).max()
            rsi = calculate_rsi(hist['Close']).iloc[-1]
            adx = calculate_adx(hist).iloc[-1]
            sma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            
            dist_sma = ((curr - sma50) / sma50) * 100
            pullback = ((curr - h3) / h3) * 100
            score, rec, reason = get_analysis(rsi, adx, dist_sma)
            
            # --- NEW: Range Calculations ---
            # Buy zone is around the SMA support line
            buy_low, buy_high = sma50 * 0.985, sma50 * 1.01
            # Sell zone is around the recent resistance (high)
            sell_low, sell_high = h3 * 0.99, h3 * 1.01
            
            results.append({
                "Ticker": symbol, 
                "Price": round(curr, 2), 
                "Score": score, 
                "Recommendation": rec, 
                "Buy Range": f"${buy_low:.2f} - ${buy_high:.2f}",
                "Sell Range": f"${sell_low:.2f} - ${sell_high:.2f}",
                "Reason": reason,
                "Trend": "🔥 Strong" if adx > 25 else "😴 Weak" if adx < 20 else "🤔 Building", 
                "ADX": round(adx, 1), "RSI": round(rsi, 1), 
                "Pullback %": round(pullback, 2), "Dist_SMA %": round(dist_sma, 2)
            })
        except: continue
    return results

def send_telegram(msg):
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

# --- Main App Execution ---
st.sidebar.markdown(f"**Current Status:** {'🟢 ACTIVE' if st.session_state.running else '🔴 STANDBY'}")

if st.session_state.running:
    data = fetch_data([t.strip().upper() for t in ticker_input.split(",")])
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df.sort_values("Score", ascending=False), use_container_width=True, hide_index=True)
        for i in data:
            if i['Score'] >= 8 or i['Recommendation'] in ["BUY", "STRONG SELL"]:
                msg = f"📣 *REC: {i['Recommendation']} ({i['Ticker']})*\nPrice: `${i['Price']}`\nBuy Zone: `{i['Buy Range']}`\nSell Zone: `{i['Sell Range']}`"
                send_telegram(msg)
    time.sleep(check_interval)
    st.rerun()
else:
    st.info("System Standby. Click **START BOT** to monitor.")

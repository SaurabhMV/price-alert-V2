import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd
import numpy as np

# --- Page Config ---
st.set_page_config(page_title="AI Confluence Trader", page_icon="🎯", layout="wide")
st.title("🎯 AI Confluence Trader: Advanced Recommendations")

# --- Sidebar: Config ---
st.sidebar.header("🔐 Access & Watchlist")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
chat_id = st.sidebar.text_input("Authorized Chat ID")
ticker_input = st.sidebar.text_input("Watchlist", value="NVDA, TSLA, AAPL, BTC-USD, AMZN")

st.sidebar.header("⚙️ Strategy Logic")
buy_drop_pct = st.sidebar.number_input("Min Pullback (%)", value=5.0)
check_interval = st.sidebar.number_input("Refresh Rate (sec)", min_value=30, value=60)

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
def get_analysis(rsi, adx, dist_sma, pullback):
    score = 0
    # 1. Momentum (RSI) - Max 4 points
    if rsi < 30: score += 4
    elif rsi < 40: score += 2
    
    # 2. Trend Strength (ADX) - Max 3 points
    if adx > 25: score += 3
    elif adx > 20: score += 1
    
    # 3. Support (Dist_SMA) - Max 3 points
    if -2 < dist_sma < 2: score += 3 
    elif dist_sma > 0: score += 1     

    # Recommendation Engine
    rec = "HOLD"
    reason = "Neutral market conditions"

    # BUY LOGIC
    if adx > 20 and dist_sma > -2 and rsi < 40:
        rec = "BUY"
        reason = "Bullish Pullback: Strong trend finding support"
    elif rsi < 30 and dist_sma < -5:
        rec = "BUY (RISKY)"
        reason = "Oversold Bounce: Mean reversion play"
    
    # SELL LOGIC
    if rsi > 70:
        rec = "SELL"
        reason = "Overbought: RSI indicates exhaustion"
    elif adx > 25 and dist_sma < -2:
        rec = "SELL / AVOID"
        reason = "Strong Downtrend: Momentum is pushing price lower"
    elif dist_sma < -5 and adx > 40:
        rec = "STRONG SELL"
        reason = "Panic Mode: High-intensity crash detected"

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
            
            score, rec, reason = get_analysis(rsi, adx, dist_sma, pullback)
            
            trend_status = "🔥 Strong" if adx > 25 else "😴 Weak" if adx < 20 else "🤔 Building"
            
            results.append({
                "Ticker": symbol, "Price": curr, "Score": score, 
                "Recommendation": rec, "Reason": reason,
                "Trend": trend_status, "ADX": round(adx, 1), 
                "RSI": round(rsi, 1), "Pullback": round(pullback, 2), 
                "Dist_SMA": round(dist_sma, 2)
            })
        except: continue
    return results

# --- Telegram Helper ---
def send_telegram(msg):
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

# --- Main App ---
if 'running' not in st.session_state: st.session_state.running = False

# Command Polling (Condensed)
if bot_token and chat_id:
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        r = requests.get(url, params={"offset": st.session_state.get('last_id', 0) + 1, "timeout": 1}).json()
        for u in r.get("result", []):
            st.session_state.last_id = u["update_id"]
            txt = u.get("message", {}).get("text", "").lower()
            if "/start" in txt: st.session_state.running = True; send_telegram("🚀 *Bot Online*")
            if "/stop" in txt: st.session_state.running = False; send_telegram("🛑 *Bot Offline*")
            if "/status" in txt: send_telegram("⌛ *Scanning watchlist...*")
    except: pass

st.sidebar.markdown(f"**Bot Status:** {'🟢 ON' if st.session_state.running else '🔴 OFF'}")

if st.session_state.running:
    data = fetch_data([t.strip().upper() for t in ticker_input.split(",")])
    if data:
        df = pd.DataFrame(data)
        
        # UI: Sorting by Score and color-coding recommendations
        st.dataframe(df.sort_values("Score", ascending=False), use_container_width=True, hide_index=True)
        
        for i in data:
            if i['Score'] >= 8 or i['Recommendation'] in ["BUY", "STRONG SELL"]:
                msg = f"📣 *REC: {i['Recommendation']} ({i['Ticker']})*\n"
                msg += f"Score: `{i['Score']}/10` | Price: `${i['Price']:.2f}`\n"
                msg += f"Reason: _{i['Reason']}_"
                send_telegram(msg)
                
    time.sleep(check_interval)
    st.rerun()
else:
    st.info("System Standby. Send `/start` to your Telegram bot.")
    time.sleep(10)
    st.rerun()

import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd
import numpy as np

# --- Page Config ---
st.set_page_config(page_title="Ultimate Trading Bot", page_icon="📈", layout="wide")
st.title("📈 Pro Trading Assistant: Buy & Sell Signals")

# --- Sidebar Configuration ---
st.sidebar.header("🎯 Strategy Settings")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
chat_id = st.sidebar.text_input("Authorized Chat ID")
ticker_input = st.sidebar.text_input("Watchlist", value="AAPL, TSLA, BTC-USD, NVDA")

col1, col2 = st.sidebar.columns(2)
with col1:
    buy_threshold = st.number_input("Buy Drop %", value=5.0)
    rsi_oversold = st.slider("RSI Oversold", 10, 40, 30)
with col2:
    sell_threshold = st.number_input("Sell Gain %", value=3.0)
    rsi_overbought = st.slider("RSI Overbought", 60, 90, 70)

check_interval = st.sidebar.number_input("Refresh Rate (sec)", min_value=30, value=60)

# --- Indicator Logic ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def fetch_signals(tickers):
    results = []
    for symbol in tickers:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period='60d', interval='1h')
            if hist.empty: continue
            
            curr = hist['Close'].iloc[-1]
            h3 = hist['High'].tail(72).max() # 3-day high
            sma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            rsi = calculate_rsi(hist['Close']).iloc[-1]
            
            # Change calculations
            pullback = ((curr - h3) / h3) * 100
            dist_sma = ((curr - sma50) / sma50) * 100
            
            # Logic: Buy Signal (Drop + Oversold)
            is_buy = pullback <= -buy_threshold and rsi <= rsi_oversold
            
            # Logic: Sell Signal (Gain over 3D High OR Overbought OR SMA Breakdown)
            is_sell_profit = (curr > h3 * (1 + sell_threshold/100)) or (rsi >= rsi_overbought)
            is_sell_loss = curr < sma50 # Trend Breakdown
            
            results.append({
                "Ticker": symbol, "Price": curr, "RSI": rsi, "SMA50": sma50,
                "Pullback": pullback, "Dist_SMA": dist_sma,
                "Buy_Signal": is_buy, "Sell_Signal": is_sell_profit or is_sell_loss,
                "Reason": "Overbought/Profit" if is_sell_profit else "SMA Breakdown" if is_sell_loss else "N/A"
            })
        except: continue
    return results

# --- Telegram with Interactive Buttons ---
def send_telegram_complex(msg, ticker):
    if not bot_token or not chat_id: return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Adding a TradingView Button
    button = {
        "inline_keyboard": [[
            {"text": "📊 View Chart", "url": f"https://www.tradingview.com/symbols/{ticker.replace('-USD', '')}"}
        ]]
    }
    
    payload = {
        "chat_id": chat_id, 
        "text": msg, 
        "parse_mode": "Markdown",
        "reply_markup": button
    }
    try: requests.post(url, json=payload)
    except: pass

# --- Bot Command Polling ---
def check_commands():
    if not bot_token or not chat_id: return False
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        r = requests.get(url, params={"offset": st.session_state.get('last_id', 0) + 1, "timeout": 1}).json()
        for u in r.get("result", []):
            st.session_state.last_id = u["update_id"]
            msg = u.get("message", {})
            if str(msg.get("chat", {}).get("id")) != str(chat_id): continue
            txt = msg.get("text", "").lower()
            if "/start" in txt: st.session_state.running = True; send_telegram_complex("🚀 Bot Started", "SPY")
            elif "/stop" in txt: st.session_state.running = False; send_telegram_complex("🛑 Bot Stopped", "SPY")
            return True
    except: pass
    return False

# --- Main App Loop ---
if 'running' not in st.session_state: st.session_state.running = False
if check_commands(): st.rerun()

st.sidebar.markdown(f"**System:** {'🟢 RUNNING' if st.session_state.running else '🔴 STOPPED'}")

if st.session_state.running:
    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
    data = fetch_signals(tickers)
    
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        for i in data:
            if i['Buy_Signal']:
                send_telegram_complex(f"🟢 *BUY SUGGESTION: {i['Ticker']}*\nPrice: ${i['Price']:.2f}\nRSI: `{i['RSI']:.1f}` (Oversold)\nPullback: `{i['Pullback']:.2f}%`", i['Ticker'])
            
            if i['Sell_Signal']:
                emoji = "🔴" if i['Reason'] == "SMA Breakdown" else "💰"
                send_telegram_complex(f"{emoji} *SELL SUGGESTION: {i['Ticker']}*\nReason: {i['Reason']}\nPrice: ${i['Price']:.2f}\nRSI: `{i['RSI']:.1f}`", i['Ticker'])

    time.sleep(check_interval)
    st.rerun()
else:
    st.info("System Standby. Use `/start` in Telegram to begin.")
    time.sleep(10)
    st.rerun()

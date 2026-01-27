import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd
import numpy as np

# --- Page Config ---
st.set_page_config(page_title="Ultimate AI Trader", page_icon="🧠", layout="wide")
st.title("🧠 Ultimate AI Trader: Trend Status & Signals")

# --- Sidebar: Credentials & Watchlist ---
st.sidebar.header("🔐 Access & Target")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
chat_id = st.sidebar.text_input("Authorized Chat ID")
ticker_input = st.sidebar.text_input("Watchlist", value="NVDA, TSLA, AAPL, BTC-USD, ZGLD.TO")

# --- Sidebar: Strategy Tuning ---
st.sidebar.header("⚙️ Strategy Logic")
col1, col2 = st.sidebar.columns(2)
with col1:
    st.markdown("### 🟢 Buy Triggers")
    buy_drop_pct = st.number_input("Min Pullback (%)", value=5.0)
    rsi_oversold = st.slider("Max RSI (Buy)", 10, 40, 30)
    min_adx = st.slider("Min Trend Strength (ADX)", 10, 50, 25)

with col2:
    st.markdown("### 🔴 Sell Triggers")
    sell_gain_pct = st.number_input("Profit Target (%)", value=3.0)
    rsi_overbought = st.slider("Min RSI (Sell)", 60, 90, 70)

check_interval = st.sidebar.number_input("Refresh Rate (seconds)", min_value=30, value=60)

# --- Session State Init ---
if 'running' not in st.session_state: st.session_state.running = False
if 'last_fetch' not in st.session_state: st.session_state.last_fetch = 0
if 'last_id' not in st.session_state: st.session_state.last_id = 0

# --- 1. Technical Indicators ---
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
    
    df['UpMove'] = df['High'] - df['High'].shift(1)
    df['DownMove'] = df['Low'].shift(1) - df['Low']
    
    df['+DM'] = np.where((df['UpMove'] > df['DownMove']) & (df['UpMove'] > 0), df['UpMove'], 0)
    df['-DM'] = np.where((df['DownMove'] > df['UpMove']) & (df['DownMove'] > 0), df['DownMove'], 0)
    
    df['+DI'] = 100 * (df['+DM'].rolling(window=period).mean() / df['TR'].rolling(window=period).mean())
    df['-DI'] = 100 * (df['-DM'].rolling(window=period).mean() / df['TR'].rolling(window=period).mean())
    df['DX'] = 100 * abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'])
    
    return df['DX'].rolling(window=period).mean()

# --- 2. Data Fetcher & Signal Engine ---
def fetch_market_data(tickers):
    results = []
    for symbol in tickers:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period='60d', interval='1h')
            if hist.empty: continue
            
            # Basic Data
            curr = hist['Close'].iloc[-1]
            h3 = hist['High'].tail(72).max()
            
            # Indicators
            hist['RSI'] = calculate_rsi(hist['Close'])
            curr_rsi = hist['RSI'].iloc[-1]
            
            sma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            dist_sma = ((curr - sma50) / sma50) * 100
            
            hist['ADX'] = calculate_adx(hist)
            curr_adx = hist['ADX'].iloc[-1]
            
            pullback = ((curr - h3) / h3) * 100
            
            # --- NEW: Interpret Trend Status ---
            if curr_adx < 20: trend_str = "😴 Weak/Choppy"
            elif curr_adx < 25: trend_str = "🤔 Building"
            elif curr_adx < 50: trend_str = "🔥 Strong"
            else: trend_str = "🚀 Super Trend"

            # Decision Logic
            signal = "HOLD"
            reason = ""
            
            if pullback <= -buy_drop_pct and curr_rsi <= rsi_oversold:
                if curr_adx >= min_adx:
                    signal = "BUY"
                    reason = f"Dip in Strong Trend"
                else:
                    signal = "WATCH"
                    reason = f"Dip but Trend Weak"

            if curr >= h3 * (1 + sell_gain_pct/100) or curr_rsi >= rsi_overbought:
                signal = "SELL"
                reason = "Profit Target / Overbought"
            elif curr < sma50 and dist_sma < -1.0:
                signal = "SELL"
                reason = "SMA Breakdown"

            results.append({
                "Ticker": symbol, "Price": curr, "Signal": signal, "Reason": reason,
                "RSI": curr_rsi, "ADX": curr_adx, "Trend_Status": trend_str, # Added this field
                "SMA_Dist": dist_sma, "Pullback": pullback
            })
        except: continue
    return results

# --- 3. Telegram & Bot Logic ---
def send_telegram(msg, ticker=None):
    if not bot_token or not chat_id: return
    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
    if ticker:
        clean = ticker.replace(".TO", "").replace("-USD", "")
        payload["reply_markup"] = {"inline_keyboard": [[{"text": f"📊 Chart", "url": f"https://www.tradingview.com/symbols/{clean}"}]]}
    try: requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)
    except: pass

def check_commands():
    if not bot_token or not chat_id: return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        r = requests.get(url, params={"offset": st.session_state.last_id + 1, "timeout": 1}).json()
        for u in r.get("result", []):
            st.session_state.last_id = u["update_id"]
            msg = u.get("message", {})
            if str(msg.get("chat", {}).get("id")) != str(chat_id).strip(): continue
            
            text = msg.get("text", "").lower()
            if "/start" in text:
                st.session_state.running = True
                send_telegram("🚀 *System Activated*")
                return True
            elif "/stop" in text:
                st.session_state.running = False
                send_telegram("🛑 *System Deactivated*")
                return True
            elif "/status" in text:
                send_telegram("⏳ *Fetching Report...*")
                data = fetch_market_data([t.strip().upper() for t in ticker_input.split(",")])
                report = "📊 *Current Market Status:*\n"
                for i in data:
                    icon = "🟢" if i['Signal'] == "BUY" else "🔴" if i['Signal'] == "SELL" else "⚪"
                    # UPDATED REPORT FORMAT
                    report += f"{icon} *{i['Ticker']}*: ${i['Price']:.2f}\n"
                    report += f"   📉 Pullback: `{i['Pullback']:.2f}%`\n"
                    report += f"   💪 Trend: `{i['Trend_Status']}` (ADX {i['ADX']:.0f})\n"
                    report += f"   📡 Signal: {i['Reason'] or 'Holding'}\n\n"
                send_telegram(report)
                return True
    except: pass
    return False

# --- 4. Main Loop ---
if check_commands(): st.rerun()

st.sidebar.markdown(f"**Status:** {'🟢 RUNNING' if st.session_state.running else '🔴 STANDBY'}")

if st.session_state.running:
    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
    now = time.time()
    if now - st.session_state.last_fetch >= check_interval:
        with st.spinner("Analyzing..."):
            data = fetch_market_data(tickers)
            st.session_state.last_fetch = now
            if data:
                # Show new column in DataFrame
                st.dataframe(pd.DataFrame(data)[['Ticker', 'Price', 'Signal', 'Trend_Status', 'ADX', 'RSI', 'Pullback']], 
                             use_container_width=True)
                
                for i in data:
                    if i['Signal'] == "BUY":
                        msg = f"🟢 *BUY ALERT: {i['Ticker']}*\n" \
                              f"📉 Pullback: `{i['Pullback']:.2f}%`\n" \
                              f"💪 Trend: `{i['Trend_Status']}`\n" \
                              f"📊 RSI: `{i['RSI']:.0f}`"
                        send_telegram(msg, i['Ticker'])
                    elif i['Signal'] == "SELL":
                        emoji = "💰" if "Profit" in i['Reason'] else "⚠️"
                        msg = f"{emoji} *SELL ALERT: {i['Ticker']}*\nReason: {i['Reason']}\nPrice: ${i['Price']:.2f}"
                        send_telegram(msg, i['Ticker'])
    time.sleep(10)
    st.rerun()
else:
    st.info("System Standby. Use `/start` to begin.")
    time.sleep(10)
    st.rerun()

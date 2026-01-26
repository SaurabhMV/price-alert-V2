import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd

# --- Page Config ---
st.set_page_config(page_title="Secure Stock Monitor", page_icon="🔒", layout="wide")
st.title("🔒 Secure Telegram-Controlled Monitor")

# --- Sidebar Credentials ---
st.sidebar.header("Security Settings")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
chat_id = st.sidebar.text_input("Your Authorized Chat ID")  # Your unique ID
ticker_input = st.sidebar.text_input("Tickers", value="AAPL, TSLA, ZGLD.TO")
drop_threshold = st.sidebar.slider("Alert Threshold (%)", 1, 20, 5)

# --- State Management ---
if 'running' not in st.session_state:
    st.session_state.running = False
if 'last_update_id' not in st.session_state:
    st.session_state.last_update_id = 0

# --- Telegram Logic ---
def send_telegram(msg):
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": msg})
        except: pass

def check_bot_commands():
    """Checks for /start or /stop ONLY from the authorized chat_id."""
    if not bot_token or not chat_id: return False
    
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {"offset": st.session_state.last_update_id + 1, "timeout": 1}
    
    try:
        response = requests.get(url, params=params).json()
        if response.get("result"):
            for update in response["result"]:
                st.session_state.last_update_id = update["update_id"]
                msg_obj = update.get("message", {})
                sender_id = str(msg_obj.get("chat", {}).get("id", ""))
                text = msg_obj.get("text", "").lower()

                # SECURITY CHECK
                if sender_id != str(chat_id).strip():
                    if "/start" in text or "/stop" in text:
                        # Optional: Let the intruder know they are blocked
                        # send_telegram_to_intruder(sender_id, "🚫 Access Denied.")
                        continue 
                
                if "/start" in text:
                    st.session_state.running = True
                    send_telegram("🚀 Authorized: Monitor Starting...")
                    return True
                elif "/stop" in text:
                    st.session_state.running = False
                    send_telegram("🛑 Authorized: Monitor Stopping...")
                    return True
    except: pass
    return False

# --- UI Controls ---
check_bot_commands() # Run on every refresh

status_color = "green" if st.session_state.running else "red"
st.sidebar.markdown(f"**Current Status:** :{status_color}[{'RUNNING' if st.session_state.running else 'STOPPED'}]")

# --- Monitoring Loop ---
if st.session_state.running:
    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
    table_placeholder = st.empty()
    
    while st.session_state.running:
        results = []
        for symbol in tickers:
            try:
                t = yf.Ticker(symbol)
                df_3d = t.history(period='3d', interval='1h')
                df_today = t.history(period='1d', interval='1m')
                
                if not df_3d.empty and not df_today.empty:
                    curr = df_today['Close'].iloc[-1]
                    h3 = df_3d['High'].max()
                    open_p = df_today['Open'].iloc[0]
                    
                    pullback = ((curr - h3) / h3) * 100
                    day_chg = ((curr - open_p) / open_p) * 100
                    
                    results.append({"Ticker": symbol, "Price": curr, "Pullback %": pullback, "Daily %": day_chg})

                    if pullback <= -drop_threshold:
                        send_telegram(f"🚨 {symbol} ALERT\nPullback: {pullback:.2f}%\nDaily Chg: {day_chg:+.2f}%")
            except: continue

        if results:
            table_placeholder.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
        
        # Check if user sent /stop during the loop
        time.sleep(60) 
        if check_bot_commands(): break 
        st.rerun()
else:
    st.info("System Standby. Bot is listening for an authorized `/start` command.")
    time.sleep(10)
    st.rerun()

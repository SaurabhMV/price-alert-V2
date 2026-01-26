import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd

# --- Page Config ---
st.set_page_config(page_title="Full Control Stock Monitor", page_icon="🏦", layout="wide")
st.title("🏦 Pro Telegram Dashboard & Remote Control")

# --- Sidebar Credentials ---
st.sidebar.header("Security & Config")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
chat_id = st.sidebar.text_input("Your Authorized Chat ID")
ticker_input = st.sidebar.text_input("Tickers", value="AAPL, TSLA, BTC-USD")
drop_threshold = st.sidebar.slider("Alert Threshold (%)", 1, 20, 5)

# --- State Management ---
if 'running' not in st.session_state:
    st.session_state.running = False
if 'last_update_id' not in st.session_state:
    st.session_state.last_update_id = 0

# --- Helper: Fetch All Data ---
def fetch_all_stock_data(tickers):
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
                
                results.append({
                    "Ticker": symbol, "Price": curr, 
                    "Pullback": pullback, "DayChg": day_chg
                })
        except: continue
    return results

# --- Telegram Logic ---
def send_telegram(msg):
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
        except: pass

def check_bot_commands():
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

                # Security Filter
                if sender_id != str(chat_id).strip(): continue 
                
                if "/start" in text:
                    st.session_state.running = True
                    send_telegram("🚀 *Monitor Started*")
                    return True
                elif "/stop" in text:
                    st.session_state.running = False
                    send_telegram("🛑 *Monitor Stopped*")
                    return True
                elif "/status" in text:
                    send_telegram("⌛ *Fetching status... please wait.*")
                    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
                    data = fetch_all_stock_data(tickers)
                    if data:
                        status_msg = "📊 *Current Watchlist Status:*\n" + "-"*20 + "\n"
                        for item in data:
                            status_msg += f"*{item['Ticker']}*: ${item['Price']:.2f}\n"
                            status_msg += f"📉 Pullback: `{item['Pullback']:.2f}%` | 📈 Day: `{item['DayChg']:+.2f}%` \n\n"
                        send_telegram(status_msg)
                    else:
                        send_telegram("❌ Could not fetch data. Check suffixes (.TO, .L).")
    except: pass
    return False

# --- UI Layout ---
check_bot_commands()
status_indicator = "🟢 RUNNING" if st.session_state.running else "🔴 STOPPED"
st.sidebar.subheader(f"System: {status_indicator}")

if st.session_state.running:
    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
    table_placeholder = st.empty()
    
    # Execution Loop
    results = fetch_all_stock_data(tickers)
    if results:
        table_placeholder.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
        for item in results:
            if item['Pullback'] <= -drop_threshold:
                send_telegram(f"🚨 *{item['Ticker']} ALERT*\nPrice: ${item['Price']:.2f}\nPullback: {item['Pullback']:.2f}%")

    time.sleep(60)
    check_bot_commands() # Final check before refresh
    st.rerun()
else:
    st.info("System Standby. Commands: `/start`, `/stop`, `/status`")
    time.sleep(10)
    st.rerun()

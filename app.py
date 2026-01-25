import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd

# --- Page Config ---
st.set_page_config(page_title="Pro Stock Monitor", page_icon="📊", layout="wide")
st.title("📈 Multi-Stock Real-Time Dashboard")

# --- Sidebar ---
st.sidebar.header("Control Panel")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
chat_id = st.sidebar.text_input("Telegram Chat ID")
ticker_input = st.sidebar.text_input("Tickers (comma separated)", value="AAPL, TSLA, NVDA")
drop_threshold = st.sidebar.slider("Alert Threshold (%)", 1, 20, 5)
check_interval = st.sidebar.number_input("Refresh Rate (seconds)", min_value=60, value=120)

def send_telegram(msg):
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": msg})
        except:
            pass

def style_df(val, threshold):
    """Applies color logic: Green (Safe), Yellow (Warning), Red (Alert)"""
    if val <= -threshold:
        return 'background-color: #ff4b4b; color: white'  # Red
    elif val <= -(threshold * 0.7):
        return 'background-color: #ffa500; color: black'  # Yellow
    return 'background-color: #2ecc71; color: white'      # Green

# --- State Control ---
if 'running' not in st.session_state:
    st.session_state.running = False

col1, col2 = st.columns(2)
if col1.button("🚀 Start Dashboard", use_container_width=True):
    st.session_state.running = True
if col2.button("🛑 Stop Dashboard", use_container_width=True):
    st.session_state.running = False

# --- Main Dashboard Loop ---
if st.session_state.running:
    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
    status_area = st.empty()
    table_area = st.empty()

    while st.session_state.running:
        results = []
        for symbol in tickers:
            try:
                t = yf.Ticker(symbol)
                # Fetch 3-day high and current price
                h3 = t.history(period='3d', interval='1h')['High'].max()
                curr = t.history(period='1d', interval='1m')['Close'].iloc[-1]
                drop = ((curr - h3) / h3) * 100
                
                results.append({"Ticker": symbol, "Price": curr, "3D High": h3, "Drop %": drop})

                if drop <= -drop_threshold:
                    send_telegram(f"🚨 ALERT: {symbol} dropped {abs(drop):.2f}% below 3-day high!")
            except Exception as e:
                st.error(f"Error loading {symbol}: {e}")
                continue

        if results:
            df = pd.DataFrame(results)
            
            # --- Status Dashboard ---
            worst_stock = df.sort_values("Drop %").iloc[0]
            with status_area.container():
                st.metric(label=f"🔥 Top Pullback: {worst_stock['Ticker']}", 
                          value=f"${worst_stock['Price']:.2f}", 
                          delta=f"{worst_stock['Drop %']:.2f}% vs 3D High")
            
            # --- Color-Coded Table ---
            styled_df = df.style.applymap(
                lambda x: style_df(x, drop_threshold), 
                subset=['Drop %']
            ).format({"Price": "${:.2f}", "3D High": "${:.2f}", "Drop %": "{:.2f}%"})
            
            table_area.dataframe(styled_df, use_container_width=True, hide_index=True)

        time.sleep(check_interval)
        st.rerun()

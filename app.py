import streamlit as st
import yfinance as yf
import time
import requests
import pandas as pd

# --- Page Config ---
st.set_page_config(page_title="Advanced Stock Monitor", page_icon="🚀", layout="wide")
st.title("📈 Pro Multi-Metric Stock Monitor")

# --- Sidebar ---
st.sidebar.header("Alert Settings")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password")
chat_id = st.sidebar.text_input("Telegram Chat ID")
ticker_input = st.sidebar.text_input("Tickers (comma separated)", value="AAPL, TSLA, NVDA, ZGLD.TO")
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
    if val <= -threshold:
        return 'background-color: #ff4b4b; color: white'  # Alert Red
    elif val <= -(threshold * 0.7):
        return 'background-color: #ffa500; color: black'  # Warning Yellow
    return 'background-color: #2ecc71; color: white'      # Safe Green

if 'running' not in st.session_state:
    st.session_state.running = False

col1, col2 = st.columns(2)
if col1.button("🚀 Start Monitoring", use_container_width=True):
    st.session_state.running = True
if col2.button("🛑 Stop Monitoring", use_container_width=True):
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
                # 1. Fetch Data
                df_3d = t.history(period='3d', interval='1h')
                df_today = t.history(period='1d', interval='1m')
                
                if not df_3d.empty and not df_today.empty:
                    # 2. Extract Prices
                    curr_price = df_today['Close'].iloc[-1]
                    high_3d = df_3d['High'].max()
                    open_price = df_today['Open'].iloc[0] # The Market Open Price
                    
                    # 3. Calculations
                    pullback_pct = ((curr_price - high_3d) / high_3d) * 100
                    daily_chg_pct = ((curr_price - open_price) / open_price) * 100
                    
                    results.append({
                        "Ticker": symbol, 
                        "Price": curr_price, 
                        "3D High": high_3d, 
                        "Drop vs 3D High": pullback_pct,
                        "Daily Chg %": daily_chg_pct
                    })

                    # 4. Trigger Alert
                    if pullback_pct <= -drop_threshold:
                        msg = (f"⚠️ {symbol} DROP ALERT!\n"
                               f"Price: ${curr_price:.2f}\n"
                               f"Pullback: {pullback_pct:.2f}% (vs 3D High)\n"
                               f"Daily Performance: {daily_chg_pct:+.2f}% (vs Open)")
                        send_telegram(msg)
                        st.toast(f"Alert sent for {symbol}!")
                else:
                    st.sidebar.warning(f"No data for {symbol}. Check suffix (e.g. .TO)")
            except:
                continue

        if results:
            df = pd.DataFrame(results)
            # Display Dashboard
            worst = df.sort_values("Drop vs 3D High").iloc[0]
            with status_area.container():
                st.metric(label=f"🔥 Top Pullback: {worst['Ticker']}", 
                          value=f"${worst['Price']:.2f}", 
                          delta=f"{worst['Drop vs 3D High']:.2f}% (Pullback)")
            
            # Apply color coding to the "Drop vs 3D High" column
            styled_df = df.style.applymap(
                lambda x: style_df(x, drop_threshold), 
                subset=['Drop vs 3D High']
            ).format({
                "Price": "${:.2f}", "3D High": "${:.2f}", 
                "Drop vs 3D High": "{:.2f}%", "Daily Chg %": "{:+.2f}%"
            })
            table_area.dataframe(styled_df, use_container_width=True, hide_index=True)

        time.sleep(check_interval)
        st.rerun()

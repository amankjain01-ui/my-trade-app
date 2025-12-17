import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import time
import random
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Dabba Gul", 
    layout="wide", 
    page_icon="📦",
    initial_sidebar_state="expanded"
)

# --- THEME: ZERODHA DARK MODE ---
st.markdown("""
    <style>
        .stApp { background-color: #0e0e0e; color: #e0e0e0; }
        [data-testid="stSidebar"] { background-color: #161616; border-right: 1px solid #333; }
        .stTextInput input, .stNumberInput input, .stSelectbox div { background-color: #262626 !important; color: white !important; border: 1px solid #444 !important; }
        .stButton button { width: 100%; border-radius: 4px; font-weight: bold; border: none; }
        .card { background-color: #1e1e1e; padding: 15px; border-radius: 8px; border: 1px solid #333; margin-bottom: 10px; }
        .text-green { color: #2ecc71; }
        .text-red { color: #e74c3c; }
    </style>
""", unsafe_allow_html=True)

# --- ASSETS CONFIG ---
BROKERAGE_PER_ORDER = 500.0 
ASSETS = {
    "Gold":       {"ticker": "GC=F", "lot": 100, "base_price": 62000},
    "Gold Mini":  {"ticker": "MGC=F", "lot": 10,  "base_price": 62000},
    "Silver":     {"ticker": "SI=F", "lot": 30,   "base_price": 74000},
    "Crude Oil":  {"ticker": "CL=F", "lot": 100,  "base_price": 6000},
    "Natural Gas":{"ticker": "NG=F", "lot": 1250, "base_price": 250},
    "Copper":     {"ticker": "HG=F", "lot": 2500, "base_price": 720},
    "Zinc":       {"ticker": "ZNc1", "lot": 5000, "base_price": 220},
    "Nifty 50":   {"ticker": "^NSEI", "lot": 50,  "base_price": 22000},
    "Bank Nifty": {"ticker": "^NSEBANK", "lot": 15, "base_price": 46000}
}

# --- DATABASE ---
def connect_db():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("My Trade DB")
    except Exception as e:
        st.error(f"DB Error: {e}")
        st.stop()

# --- DATA FUNCTIONS ---
def get_users():
    try: return pd.DataFrame(connect_db().worksheet("Users").get_all_records())
    except: return pd.DataFrame()

def update_user_balance(username, new_balance):
    try:
        ws = connect_db().worksheet("Users")
        cell = ws.find(username)
        ws.update_cell(cell.row, 3, new_balance)
    except: pass

def log_trade(order_dict):
    connect_db().worksheet("Orders").append_row(list(order_dict.values()))

def update_portfolio(user, symbol, qty, price, action):
    ws = connect_db().worksheet("Portfolio")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    key = f"{user}_{symbol}"
    if not df.empty and key in df['User_Symbol'].values:
        row_idx = df.index[df['User_Symbol'] == key][0] + 2
        curr_qty = df.iloc[df.index[df['User_Symbol'] == key][0]]['Qty']
        new_qty = curr_qty + qty if action == "BUY" else curr_qty - qty
        if new_qty <= 0: ws.delete_rows(int(row_idx))
        else: ws.update_cell(int(row_idx), 4, int(new_qty))
    elif action == "BUY":
        ws.append_row([key, user, symbol, qty, price])

# --- SIMULATION ENGINE (THE FIX FOR BLANK CHARTS) ---
def generate_mock_data(symbol, periods=50):
    """Generates realistic fake candle data if Yahoo fails"""
    base = ASSETS[symbol]["base_price"]
    
    # Create time index
    end_time = datetime.now()
    times = [end_time - timedelta(minutes=5*i) for i in range(periods)]
    times.reverse()
    
    # Random Walk
    prices = [base]
    for _ in range(periods-1):
        change = random.uniform(-0.002, 0.002) # 0.2% fluctuation
        prices.append(prices[-1] * (1 + change))
        
    df = pd.DataFrame({
        'Close': prices,
        'Open': [p * (1 + random.uniform(-0.001, 0.001)) for p in prices],
        'High': [p * (1 + random.uniform(0, 0.001)) for p in prices],
        'Low': [p * (1 - random.uniform(0, 0.001)) for p in prices],
        'Volume': [random.randint(100, 1000) for _ in range(periods)]
    }, index=times)
    
    return df

def get_market_data(symbol):
    ticker = ASSETS[symbol]["ticker"]
    
    # 1. Try Real Data
    try:
        data = yf.download(ticker, period="1d", interval="15m", progress=False)
        if len(data) > 5:
            # Add live noise to last candle
            last_price = data['Close'].iloc[-1].item()
            noise = last_price * 0.0002
            live_price = last_price + random.uniform(-noise, noise)
            
            # Convert Yahoo USD to approximate INR for display
            if "NSE" not in ticker and "ZNc1" not in ticker: 
                live_price = live_price * 84.0 # USD conversion
            
            return round(live_price, 2), data
    except:
        pass
    
    # 2. Fallback to Mock Data (If Real fails)
    data = generate_mock_data(symbol)
    live_price = data['Close'].iloc[-1]
    return round(live_price, 2), data

def render_chart(symbol, data):
    # Determine colors based on Trend
    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'], high=data['High'],
        low=data['Low'], close=data['Close'],
        name="Price",
        increasing_line_color='#2ecc71', decreasing_line_color='#e74c3c'
    ))

    # Layout
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1e1e1e",
        plot_bgcolor="#1e1e1e",
        height=450,
        margin=dict(l=0, r=40, t=30, b=0),
        xaxis_rangeslider_visible=False,
        showlegend=False,
        title=f"{symbol} - Live (Simulated View)"
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# --- LOGIN ---
if 'user' not in st.session_state:
    st.markdown("<br><h1 style='text-align: center; color: #e74c3c;'>📦 Dabba Gul Login</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("ENTER MARKET"):
                df = get_users()
                if not df.empty and u in df['Username'].values:
                    user_row = df[df['Username'] == u].iloc[0]
                    if str(user_row['Password']) == str(p):
                        st.session_state.user = u
                        st.session_state.balance = float(user_row['Balance'])
                        st.rerun()
                    else: st.error("Wrong Password")
                else: st.error("User Not Found")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header(f"👤 {st.session_state.user}")
    if st.checkbox("🔴 Auto-Refresh", value=True):
        st_autorefresh(interval=3000, key="refresher")
    
    st.divider()
    st.caption("WATCHLIST")
    for asset in ASSETS:
        price, _ = get_market_data(asset)
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{asset}**")
        color = "#2ecc71" if random.random() > 0.5 else "#e74c3c"
        c2.markdown(f"<span style='color:{color}'>₹{price:,.0f}</span>", unsafe_allow_html=True)
    
    st.divider()
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- HEADER ---
st.markdown(f"""
    <div class="card" style="display: flex; justify_content: space-between; align-items: center;">
        <div><span style="color: #888;">Funds Available</span><h2 style="color: #2ecc71; margin:0;">₹{st.session_state.balance:,.2f}</h2></div>
        <div><h1 style="color: #e74c3c; margin:0;">📦 Dabba Gul</h1></div>
    </div>
""", unsafe_allow_html=True)

# --- MAIN WORKSPACE ---
col1, col2 = st.columns([3, 1])

with col1:
    # Asset Selection
    selected_asset = st.selectbox("Select Scrip", list(ASSETS.keys()))
    price, chart_data = get_market_data(selected_asset)
    
    st.markdown(f"<h2 style='margin:0;'>₹{price:,.2f} <span style='font-size:16px; color:#888'>LTP</span></h2>", unsafe_allow_html=True)
    render_chart(selected_asset, chart_data)

with col2:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Order Window")
    with st.form("order"):
        qty = st.number_input("Lots", 1, 100, 1)
        action = st.radio("Side", ["BUY", "SELL"], horizontal=True)
        
        val = price * qty * ASSETS[selected_asset]['lot']
        st.markdown(f"**Margin:** ₹{val:,.0f}")
        st.caption("Brokerage: ₹500")
        
        if st.form_submit_button("⚡ TRADE"):
            cost = val + BROKERAGE_PER_ORDER if action == "BUY" else val - BROKERAGE_PER_ORDER
            if action == "BUY" and st.session_state.balance < cost:
                st.error("No Money!")
            else:
                new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
                update_user_balance(st.session_state.user, new_bal)
                log_

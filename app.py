import streamlit as st
import pandas as pd
import numpy as np
import time
import random
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# --- 1. PAGE CONFIG ---
st.set_page_config(
    page_title="Dabba Gul Live", 
    layout="wide", 
    page_icon="📦",
    initial_sidebar_state="expanded"
)

# --- 2. THEME: VINTAGE DARK (High Contrast) ---
st.markdown("""
    <style>
        .stApp { background-color: #050505; color: #ffb700; font-family: 'Courier New', monospace; }
        [data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
        
        /* INPUTS */
        .stTextInput input, .stNumberInput input, .stSelectbox div { 
            background-color: #000 !important; color: #ffb700 !important; 
            border: 1px solid #444 !important; border-radius: 0px;
        }
        
        /* BUTTONS */
        .stButton button {
            background-color: #ffb700; color: #000; font-weight: bold; border: none; border-radius: 0px;
        }
        .stButton button:hover { background-color: #d49a00; }
        
        /* TEXT COLORS */
        .up { color: #00ff00 !important; }
        .down { color: #ff3333 !important; }
        .amber { color: #ffb700 !important; }
        
        /* TABLES */
        table { width: 100%; border-collapse: collapse; border: 1px solid #333; }
        th { background-color: #222; padding: 10px; text-align: left; color: #888; }
        td { background-color: #111; padding: 10px; border-bottom: 1px solid #222; }
    </style>
""", unsafe_allow_html=True)

# --- 3. EXACT ASSETS (From Screenshot) ---
# Format: Name: {Lot Size, Starting Price}
ASSETS = {
    "Gold 05Feb":      {"lot": 100, "start": 134230.00},
    "Silver 05Mar":    {"lot": 30,  "start": 204172.00},
    "Crude Oil 18Dec": {"lot": 100, "start": 5074.00},
    "Copper 31Dec":    {"lot": 2500,"start": 1108.50},
    "Aluminium 31Dec": {"lot": 5000,"start": 280.80},
    "Zinc 31Dec":      {"lot": 5000,"start": 303.25},
    "Gold Mini 05Jan": {"lot": 10,  "start": 132605.00},
    "Silver Mini 27Feb":{"lot": 1,   "start": 204660.00},
    "USDINR":          {"lot": 1000,"start": 90.36}
}

# --- 4. SESSION STATE ---
if 'balance' not in st.session_state: st.session_state.balance = 0.0
if 'user' not in st.session_state: st.session_state.user = None

# Initialize Prices
if 'prices' not in st.session_state:
    st.session_state.prices = {k: v['start'] for k, v in ASSETS.items()}

# Initialize Pending Orders List
if 'pending' not in st.session_state:
    st.session_state.pending = []

# Initialize History (For Candles)
if 'history' not in st.session_state:
    st.session_state.history = {}
    for sym, start in st.session_state.prices.items():
        times = [datetime.now() - timedelta(minutes=i*15) for i in range(50)]
        times.reverse()
        # Create fake candle history
        highs, lows, opens, closes = [], [], [], []
        curr = start
        for _ in range(50):
            o = curr * (1 + random.uniform(-0.0005, 0.0005))
            c = o * (1 + random.uniform(-0.0005, 0.0005))
            h = max(o, c) * (1 + random.uniform(0, 0.0002))
            l = min(o, c) * (1 - random.uniform(0, 0.0002))
            opens.append(o); closes.append(c); highs.append(h); lows.append(l)
            curr = c
        
        st.session_state.history[sym] = {
            'time': times, 'open': opens, 'high': highs, 'low': lows, 'close': closes
        }

# --- 5. CORE LOGIC (Run Every Refresh) ---
def logic_engine():
    # 1. Simulate Price Ticks
    for sym in st.session_state.prices:
        last = st.session_state.prices[sym]
        # Random small tick
        change = last * random.uniform(-0.0001, 0.0001)
        new_price = last + change
        st.session_state.prices[sym] = new_price
        
        # Update Chart Data (Append new candle data)
        h = st.session_state.history[sym]
        h['time'].append(datetime.now())
        h['open'].append(last)
        h['close'].append(new_price)
        h['high'].append(max(last, new_price))
        h['low'].append(min(last, new_price))
        
        # Keep list short
        if len(h['time']) > 60:
            for key in h: h[key].pop(0)

    # 2. CHECK LIMIT ORDERS
    executed_indices = []
    for i, order in enumerate(st.session_state.pending):
        sym = order['Symbol']
        ltp = st.session_state.prices[sym]
        trigger = False
        
        # LIMIT BUY: Market Price drops BELOW Limit Price
        if order['Type'] == "LIMIT" and order['Action'] == "BUY" and ltp <= order['Price']: trigger = True
        # LIMIT SELL: Market Price goes ABOVE Limit Price
        elif order['Type'] == "LIMIT" and order['Action'] == "SELL" and ltp >= order['Price']: trigger = True
        # SL BUY: Market Price goes ABOVE Trigger
        elif order['Type'] == "SL" and order['Action'] == "BUY" and ltp >= order['Price']: trigger = True
        # SL SELL: Market Price drops BELOW Trigger
        elif order['Type'] == "SL" and order['Action'] == "SELL" and ltp <= order['Price']: trigger = True
        
        if trigger:
            success = process_trade(order['User'], sym, order['Action'], order['Qty'], ltp)
            if success:
                executed_indices.append(i)
                # Show toast notification
                st.toast(f"✅ ORDER FILLED: {order['Action']} {sym} @ {ltp:.2f}")

    # Remove executed orders (reverse order to avoid index shift)
    for i in sorted(executed_indices, reverse=True):
        st.session_state.pending.pop(i)

def process_trade(user, symbol, action, qty, price):
    lot = ASSETS[symbol]['lot']
    val = price * qty * lot
    cost = val + 500.0 if action == "BUY" else val - 500.0
    
    # Funds Check (Only for Buy)
    if action == "BUY" and st.session_state.balance < cost:
        return False
        
    # Update Balance
    new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
    st.session_state.balance = new_bal
    
    # DB Sync
    update_db_balance(user, new_bal)
    log_trade_db({
        'Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'User': user, 'Symbol': symbol,
        'Action': action, 'Qty': qty, 'Price': price, 'Val': val, 'Type': 'FILLED'
    })
    update_portfolio_db(user, symbol, qty, price, action)
    return True

# --- 6. DB HELPERS ---
def connect_db():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("My Trade DB")
    except: return None

def get_users():
    try: return pd.DataFrame(connect_db().worksheet("Users").get_all_records())
    except: return pd.DataFrame()

def update_db_balance(user, val):
    try: ws = connect_db().worksheet("Users"); cell = ws.find(user); ws.update_cell(cell.row, 3, val)
    except: pass

def log_trade_db(d):
    try: connect_db().worksheet("Orders").append_row(list(d.values()))
    except: pass

def update_portfolio_db(user, symbol, qty, price, action):
    try:
        ws = connect_db().worksheet("Portfolio")
        df = pd.DataFrame(ws.get_all_records())
        key = f"{user}_{symbol}"
        if not df.empty and key in df['User_Symbol'].values:
            idx = df.index[df['User_Symbol'] == key][0] + 2
            curr = df.iloc[idx-2]['Qty']
            new_q = curr + qty if action == "BUY" else curr - qty
            if new_q <= 0: ws.delete_rows(int(idx))
            else: ws.update_cell(int(idx), 4, int(new_q))
        elif action == "BUY": ws.append_row([key, user, symbol, qty, price])
    except: pass

# --- 7. LOGIN ---
if st.session_state.user is None:
    st.markdown("<br><h1 style='text-align:center; color:#ffb700'>📦 DABBA GUL LOGIN</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            u = st.text_input("USER ID")
            p = st.text_input("PASSWORD", type="password")
            if st.form_submit_button("LOGIN"):
                df = get_users()
                if not df.empty and u in df['Username'].values:
                    row = df[df['Username']==u].iloc[0]
                    if str(row['Password']) == str(p):
                        st.session_state.user = u
                        st.session_state.balance = float(row['Balance'])
                        st.rerun()
                    else: st.error("WRONG PASSWORD")
                else: st.error("USER NOT FOUND")
    st.stop()

# --- 8. MAIN APP ---
logic_engine() # Run Logic
st_autorefresh(interval=1000, key="refresher") # Auto-Refresh Page every 1s

# SIDEBAR
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.user}")
    st.markdown("---")
    
    # 1. CALIBRATION PANEL (To fix rates instantly)
    with st.expander("🔧 FIX RATES (Admin)", expanded=True):
        st.caption("Type real price to sync:")
        for s in st.session_state.prices:
            new_v = st.number_input(s, value=float(st.session_state.prices[s]), key=f"cal_{s}")
            if abs(new_v - st.session_state.prices[s]) > 0.5:
                st.session_state.prices[s] = new_v
                st.rerun()

    st.markdown("### WATCHLIST")
    for s, p in st.session_state.prices.items():
        # Random daily change styling
        chg = random.uniform(-0.5, 0.5)
        clr = "#00ff00" if chg > 0 else "#ff3333"
        st.markdown(f"<div style='display:flex; justify-content:space-between; border-bottom:1px solid #333; padding:5px;'><span style='color:#ccc'>{s}</span><span style='color:{clr}'>{p:,.2f}</span></div>", unsafe_allow_html=True)

    if st.button("LOGOUT"): st.session_state.clear(); st.rerun()

# HEADER
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown(f"<span style='color:#888'>AVAILABLE FUNDS</span><br><span style='font-size:36px; color:#ffb700; font-weight:bold;'>₹{st.session_state.balance:,.2f}</span>", unsafe_allow_html=True)

# TRADING AREA
col1, col2 = st.columns([2.5, 1])

with col1:
    # Asset Selector
    sel = st.selectbox("SELECT ASSET", list(ASSETS.keys()))
    curr = st.session_state.prices[sel]
    
    st.markdown(f"<span style='font-size:42px; font-weight:bold; color:white;'>{curr:,.2f}</span> <span class='up'>LIVE</span>", unsafe_allow_html=True)
    
    # Candlestick Chart
    h = st.session_state.history[sel]
    fig = go.Figure(data=[go.Candlestick(
        x=h['time'], open=h['open'], high=h['high'], low=h['low'], close=h['close'],
        increasing_line_color='#00ff00', decreasing_line_color='#ff3333'
    )])
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#050505", plot_bgcolor="#050505",
        height=500, margin=dict(t=20, b=20, l=0, r=40), xaxis_rangeslider_visible=False
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with col2:
    st.markdown("<div style='background:#111; padding:15px; border:1px solid #ffb700;'>", unsafe_allow_html=True)
    st.subheader("PLACE ORDER")
    
    with st.form("order_form"):
        qty = st.number_input("LOTS", 1, 100, 1)
        type_ = st.radio("TYPE", ["MARKET", "LIMIT", "SL"], horizontal=True)
        # Limit Price Input
        limit_px = st.number_input("PRICE", value=float(curr))
        action = st.radio("SIDE", ["BUY", "SELL"], horizontal=True)
        
        lot = ASSETS[sel]['lot']
        est_val = (limit_px if type_ != "MARKET" else curr) * qty * lot
        
        st.markdown("---")
        st.caption(f"REQ MARGIN: ₹{est_val:,.0f} | LOT: {lot}")
        
        if st.form_submit_button("SUBMIT ORDER"):
            if type_ == "MARKET":
                success = process_trade(st.session_state.user, sel, action, qty, curr)
                if success: st.success("FILLED")
                else: st.error("NO FUNDS")
            else:
                # Add to Pending
                st.session_state.pending.append({
                    'User': st.session_state.user, 'Symbol': sel, 'Action': action,
                    'Qty': qty, 'Type': type_, 'Price': limit_px
                })
                st.info("ORDER QUEUED")
                
    st.markdown("</div>", unsafe_allow_html=True)

# TABS
t1, t2 = st.tabs(["OPEN POSITIONS", "PENDING ORDERS"])

with t1:
    try:
        df = pd.DataFrame(connect_db().worksheet("Portfolio").get_all_records())
        if not df.empty:
            my = df[df['User'] == st.session_state.user]
            if not my.empty:
                rows = ""
                total_pnl = 0.0
                for _, r in my.iterrows():
                    ltp = st.session_state.prices.get(r['Symbol'], r['Avg_Price'])
                    ls = ASSETS.get(r['Symbol'], {'lot':1})['lot']
                    pnl = (ltp - r['Avg_Price']) * r['Qty'] * ls
                    total_pnl += pnl
                    c = "up" if pnl >= 0 else "down"
                    rows += f"<tr><td>{r['Symbol']}</td><td>{r['Qty']}</td><td>{r['Avg_Price']:.2f}</td><td class='{c}'>{pnl:,.2f}</td></tr>"
                
                st.markdown(f"<table><tr><th>SCRIPT</th><th>QTY</th><th>AVG</th><th>P&L</th></tr>{rows}</table>", unsafe_allow_html=True)
                st.markdown(f"<div style='text-align:center; padding:10px; font-size:24px; font-weight:bold;' class='{'up' if total_pnl>=0 else 'down'}'>TOTAL P&L: ₹{total_pnl:,.2f}</div>", unsafe_allow_html=True)
            else: st.info("No Positions")
        else: st.info("No Positions")
    except: pass

with t2:
    if st.session_state.pending:
        # Show table of pending orders
        pending_df = pd.DataFrame(st.session_state.pending)
        st.dataframe(pending_df[['Symbol', 'Action', 'Type', 'Price', 'Qty']], use_container_width=True)
        if st.button("CANCEL ALL"):
            st.session_state.pending = []
            st.rerun()
    else:
        st.info("No Pending Orders")

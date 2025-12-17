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

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Dabba Gul Terminal", 
    layout="wide", 
    page_icon="📦",
    initial_sidebar_state="expanded"
)

# --- 2. THEME: REALISTIC VINTAGE (Retro Terminal) ---
st.markdown("""
    <style>
        /* MAIN BACKGROUND - Retro Black */
        .stApp { background-color: #0d0d0d; color: #ffb000; font-family: 'Courier New', Courier, monospace; }
        
        /* SIDEBAR */
        [data-testid="stSidebar"] { background-color: #1a1a1a; border-right: 2px solid #ffb000; }
        
        /* INPUTS */
        .stTextInput input, .stNumberInput input, .stSelectbox div { 
            background-color: #000; color: #ffb000 !important; border: 1px solid #ffb000 !important; 
            border-radius: 0px; font-family: 'Courier New';
        }
        
        /* BUTTONS */
        .stButton button {
            background-color: #000; color: #ffb000; border: 2px solid #ffb000;
            text-transform: uppercase; font-weight: bold; border-radius: 0px;
            box-shadow: 0 0 5px #ffb000;
        }
        .stButton button:hover { background-color: #ffb000; color: #000; }
        
        /* TEXT COLORS */
        .text-green { color: #00ff41 !important; text-shadow: 0 0 5px #00ff41; }
        .text-red { color: #ff3333 !important; text-shadow: 0 0 5px #ff3333; }
        .text-amber { color: #ffb000 !important; }
        
        /* BIG PRICE */
        .big-price { font-size: 42px; font-weight: bold; text-shadow: 0 0 10px #ffb000; }
        
        /* TABLES */
        table { width: 100%; border-collapse: collapse; border: 1px solid #444; }
        th { background-color: #222; color: #aaa; padding: 10px; border-bottom: 2px solid #ffb000; text-align: left;}
        td { background-color: #111; color: #ddd; padding: 8px; border-bottom: 1px solid #333; font-family: 'Courier New'; }
        
        /* TABS */
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] { background-color: #222; color: #ffb000; border: 1px solid #444; }
        .stTabs [aria-selected="true"] { background-color: #ffb000; color: #000; border: 1px solid #ffb000; }
    </style>
""", unsafe_allow_html=True)

# --- 3. ALL MCX COMMODITY SCRIPTS (Live Rates Dec 2025) ---
ASSETS_INFO = {
    # PRECIOUS METALS
    "GOLD 1KG":       {"lot": 100, "start": 76520.00},
    "GOLD MINI":      {"lot": 10,  "start": 76520.00},
    "GOLD GUINEA":    {"lot": 8,   "start": 61200.00},
    "GOLD PETAL":     {"lot": 1,   "start": 7650.00},
    "SILVER 30KG":    {"lot": 30,  "start": 91250.00},
    "SILVER MINI":    {"lot": 5,   "start": 91250.00},
    "SILVER MICRO":   {"lot": 1,   "start": 91250.00},
    
    # ENERGY
    "CRUDE OIL":      {"lot": 100, "start": 5945.00},
    "CRUDE OIL MINI": {"lot": 10,  "start": 5945.00},
    "NATURAL GAS":    {"lot": 1250,"start": 248.10},
    "NAT GAS MINI":   {"lot": 250, "start": 248.10},
    
    # BASE METALS
    "COPPER":         {"lot": 2500,"start": 862.50},
    "ZINC":           {"lot": 5000,"start": 275.40},
    "ZINC MINI":      {"lot": 1000,"start": 275.40},
    "ALUMINIUM":      {"lot": 5000,"start": 235.10},
    "ALUMINI":        {"lot": 1000,"start": 235.10},
    "LEAD":           {"lot": 5000,"start": 185.30},
    "LEAD MINI":      {"lot": 1000,"start": 185.30},
    
    # AGRI
    "MENTHA OIL":     {"lot": 360, "start": 940.00}
}

# --- 4. SESSION STATE & ENGINE ---
if 'balance' not in st.session_state: st.session_state.balance = 0.0
if 'user' not in st.session_state: st.session_state.user = None
if 'prices' not in st.session_state:
    st.session_state.prices = {k: v['start'] for k, v in ASSETS_INFO.items()}
if 'pending_orders' not in st.session_state:
    st.session_state.pending_orders = []

# Initialize Chart History
if 'history' not in st.session_state:
    st.session_state.history = {}
    for sym, start in st.session_state.prices.items():
        times = [datetime.now() - timedelta(minutes=i) for i in range(60)]
        times.reverse()
        prices = [start]
        for _ in range(59):
            prices.append(prices[-1] * (1 + random.uniform(-0.0005, 0.0005)))
        st.session_state.history[sym] = {'times': times, 'prices': prices}

# --- 5. CORE LOGIC (Updates Every Second) ---
def update_market():
    # 1. Update Prices (Random Walk)
    for sym in st.session_state.prices:
        current = st.session_state.prices[sym]
        tick = current * random.uniform(-0.0002, 0.0002) 
        new_price = current + tick
        st.session_state.prices[sym] = new_price
        
        # Update Chart Data
        st.session_state.history[sym]['times'].append(datetime.now())
        st.session_state.history[sym]['prices'].append(new_price)
        if len(st.session_state.history[sym]['prices']) > 100:
            st.session_state.history[sym]['prices'].pop(0)
            st.session_state.history[sym]['times'].pop(0)

    # 2. Check Pending Orders (Limit/SL)
    executed = []
    for order in st.session_state.pending_orders:
        ltp = st.session_state.prices[order['Symbol']]
        trigger = False
        
        if order['Type'] == "LIMIT":
            if order['Action'] == "BUY" and ltp <= order['Price']: trigger = True
            if order['Action'] == "SELL" and ltp >= order['Price']: trigger = True
        elif order['Type'] == "SL":
            if order['Action'] == "BUY" and ltp >= order['Price']: trigger = True
            if order['Action'] == "SELL" and ltp <= order['Price']: trigger = True
            
        if trigger:
            execute_trade(order['User'], order['Symbol'], order['Action'], order['Qty'], ltp, "EXECUTED")
            executed.append(order)
            
    for ex in executed:
        if ex in st.session_state.pending_orders:
            st.session_state.pending_orders.remove(ex)

def execute_trade(user, symbol, action, qty, price, status):
    lot = ASSETS_INFO[symbol]['lot']
    val = price * qty * lot
    cost = val + 500.0 if action == "BUY" else val - 500.0
    
    if action == "BUY" and st.session_state.balance < cost and status == "EXECUTED":
        return False # Fail due to funds

    if status == "EXECUTED":
        new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
        st.session_state.balance = new_bal
        update_db_balance(user, new_bal)
        update_portfolio_db(user, symbol, qty, price, action)
        log_trade_db({
            'Time': datetime.now().strftime("%H:%M:%S"), 'User': user, 'Symbol': symbol,
            'Action': action, 'Qty': qty, 'Price': price, 'Type': "FILLED", 'Value': val
        })
    return True

# --- 6. DATABASE ---
def connect_db():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("My Trade DB")
    except: st.stop()

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
    st.markdown("<br><h1 style='text-align:center; color:#ffb000;'>📦 DABBA GUL LOGIN</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            u = st.text_input("OPERATOR ID")
            p = st.text_input("ACCESS CODE", type="password")
            if st.form_submit_button("CONNECT"):
                df = get_users()
                if not df.empty and u in df['Username'].values:
                    row = df[df['Username']==u].iloc[0]
                    if str(row['Password']) == str(p):
                        st.session_state.user = u
                        st.session_state.balance = float(row['Balance'])
                        st.rerun()
                    else: st.error("ACCESS DENIED")
                else: st.error("UNKNOWN USER")
    st.stop()

# --- 8. MAIN UI ---
update_market() # Run Logic
st_autorefresh(interval=1000, key="auto_update") # Live Refresh

# SIDEBAR
with st.sidebar:
    st.markdown(f"### OPERATOR: {st.session_state.user}")
    
    with st.expander("🔧 PRICE CALIBRATION"):
        for s in st.session_state.prices:
            new_v = st.number_input(s, value=float(st.session_state.prices[s]), format="%.2f")
            if abs(new_v - st.session_state.prices[s]) > 1: st.session_state.prices[s] = new_v

    st.markdown("### 📟 LIVE FEED")
    for sym, price in st.session_state.prices.items():
        change = random.choice([1, -1])
        color = "#00ff41" if change > 0 else "#ff3333"
        st.markdown(f"<div style='border-bottom:1px dashed #444; padding:4px; display:flex; justify-content:space-between;'><span style='color:#ccc'>{sym}</span><span style='color:{color}'>{price:,.2f}</span></div>", unsafe_allow_html=True)
    
    if st.button("LOGOUT"): st.session_state.clear(); st.rerun()

# HEADER
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown(f"<span style='color:#888'>FUNDS AVAILABLE</span><br><span class='big-price text-amber'>₹{st.session_state.balance:,.2f}</span>", unsafe_allow_html=True)

# WORKSPACE
col_chart, col_order = st.columns([2.5, 1])

with col_chart:
    selected = st.selectbox("SELECT SCRIPT", list(st.session_state.prices.keys()))
    curr_price = st.session_state.prices[selected]
    
    st.markdown(f"<span class='big-price'>₹{curr_price:,.2f}</span> <span class='text-green'>LIVE</span>", unsafe_allow_html=True)
    
    # Retro Chart
    data = st.session_state.history[selected]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data['times'], y=data['prices'], mode='lines', line=dict(color='#ffb000', width=2), fill='tozeroy', fillcolor='rgba(255, 176, 0, 0.1)'))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#0d0d0d", plot_bgcolor="#0d0d0d", height=450, margin=dict(t=20, b=20, l=10, r=10), xaxis=dict(showgrid=True, gridcolor='#333'), yaxis=dict(showgrid=True, gridcolor='#333', side='right'))
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with col_order:
    st.markdown("<div style='background:#1a1a1a; padding:15px; border:2px solid #ffb000;'>", unsafe_allow_html=True)
    st.subheader("COMMAND ENTRY")
    
    with st.form("entry"):
        qty = st.number_input("LOTS", 1, 100, 1)
        ord_type = st.radio("TYPE", ["MARKET", "LIMIT", "SL"], horizontal=True)
        limit_px = st.number_input("PRICE (Limit/SL)", value=float(curr_price))
        action = st.radio("ACTION", ["BUY", "SELL"], horizontal=True)
        
        lot = ASSETS_INFO[selected]['lot']
        val = (limit_px if ord_type != "MARKET" else curr_price) * qty * lot
        
        st.markdown("---")
        st.caption(f"REQ MARGIN: ₹{val:,.0f} | LOT: {lot}")
        
        if st.form_submit_button("TRANSMIT ORDER"):
            if ord_type == "MARKET":
                success = execute_trade(st.session_state.user, selected, action, qty, curr_price, "EXECUTED")
                if success: st.success("FILLED")
                else: st.error("NO FUNDS")
            else:
                st.session_state.pending_orders.append({'User': st.session_state.user, 'Symbol': selected, 'Action': action, 'Qty': qty, 'Type': ord_type, 'Price': limit_px})
                st.info("ORDER QUEUED")
                
    st.markdown("</div>", unsafe_allow_html=True)

# POSITIONS & ORDERS
tab1, tab2 = st.tabs(["OPEN POSITIONS", "OPEN ORDERS"])

with tab1:
    try:
        df_port = pd.DataFrame(connect_db().worksheet("Portfolio").get_all_records())
        if not df_port.empty:
            my_port = df_port[df_port['User'] == st.session_state.user]
            if not my_port.empty:
                rows = ""
                total_pnl = 0.0
                for _, row in my_port.iterrows():
                    ltp = st.session_state.prices.get(row['Symbol'], row['Avg_Price'])
                    ls = ASSETS_INFO.get(row['Symbol'], {'lot':1})['lot']
                    pnl = (ltp - row['Avg_Price']) * row['Qty'] * ls
                    total_pnl += pnl
                    color = "text-green" if pnl >= 0 else "text-red"
                    rows += f"<tr><td>{row['Symbol']}</td><td>{row['Qty']}</td><td>{row['Avg_Price']:.2f}</td><td>{ltp:.2f}</td><td class='{color}'>{pnl:,.2f}</td></tr>"
                
                st.markdown(f"<table><tr><th>SCRIPT</th><th>QTY</th><th>AVG</th><th>LTP</th><th>P&L</th></tr>{rows}</table>", unsafe_allow_html=True)
                st.markdown(f"<div style='margin-top:10px; padding:10px; background:#222; text-align:center; border:1px solid #444;'>TOTAL P&L: <span class='{'text-green' if total_pnl>=0 else 'text-red'}' style='font-size:24px; font-weight:bold;'>₹{total_pnl:,.2f}</span></div>", unsafe_allow_html=True)
            else: st.info("NO POSITIONS")
        else: st.info("NO POSITIONS")
    except: pass

with tab2:
    if st.session_state.pending_orders:
        odf = pd.DataFrame(st.session_state.pending_orders)
        st.dataframe(odf[['Symbol', 'Action', 'Type', 'Price', 'Qty']])
        if st.button("CANCEL ALL ORDERS"):
            st.session_state.pending_orders = []
            st.rerun()
    else: st.info("NO PENDING ORDERS")

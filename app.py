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
    page_title="Dabba Gul", 
    layout="wide", 
    page_icon="📦",
    initial_sidebar_state="expanded"
)

# --- 2. THEME: REALISTIC VINTAGE (Retro Terminal Style) ---
st.markdown("""
    <style>
        /* MAIN BACKGROUND - Retro Black */
        .stApp { background-color: #1a1a1a; color: #ffb000; font-family: 'Courier New', Courier, monospace; }
        
        /* SIDEBAR - Dark Grey */
        [data-testid="stSidebar"] { background-color: #2b2b2b; border-right: 2px solid #ffb000; }
        
        /* INPUT FIELDS - Old Computer Style */
        .stTextInput input, .stNumberInput input, .stSelectbox div { 
            background-color: #000000 !important; 
            color: #ffb000 !important; 
            border: 1px solid #ffb000 !important; 
            border-radius: 0px;
            font-family: 'Courier New', Courier, monospace;
        }
        
        /* BUTTONS - Amber Glow */
        .stButton button {
            background-color: #000000;
            color: #ffb000;
            font-weight: bold;
            border: 2px solid #ffb000;
            border-radius: 0px;
            text-transform: uppercase;
            box-shadow: 0 0 5px #ffb000;
        }
        .stButton button:hover {
            background-color: #ffb000;
            color: #000000;
        }
        
        /* CARDS - Vintage Paper/Terminal */
        .vintage-card {
            background-color: #222;
            padding: 15px;
            border: 2px dashed #555;
            margin-bottom: 15px;
        }
        
        /* TEXT COLORS */
        .text-amber { color: #ffb000; }
        .text-green { color: #00ff41; } /* Matrix Green */
        .text-red { color: #ff3333; }   /* Retro Red */
        
        /* HEADERS */
        h1, h2, h3 { border-bottom: 1px solid #555; padding-bottom: 5px; }
        
        /* BIG PRICE */
        .big-price { 
            font-size: 42px; 
            font-weight: bold; 
            font-family: 'Courier New', monospace; 
            text-shadow: 0 0 5px #ffb000;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. ASSETS (Futures & Options Contracts) ---
ASSETS_INFO = {
    "Gold 05Feb Fut":      {"lot": 100, "start": 76500.00, "type": "FUT"},
    "Silver 05Mar Fut":    {"lot": 30,  "start": 91200.00, "type": "FUT"},
    "Crude Oil 19Dec Fut": {"lot": 100, "start": 5950.00, "type": "FUT"},
    "Nifty 21Dec 24000 CE":{"lot": 50,  "start": 150.00, "type": "OPT"},
    "Nifty 21Dec 24000 PE":{"lot": 50,  "start": 120.00, "type": "OPT"},
    "BankNifty 25Dec 51000 CE":{"lot": 15, "start": 340.00, "type": "OPT"},
    "Gold Mini 05Jan Fut": {"lot": 10,  "start": 76200.00, "type": "FUT"}
}

# --- 4. SESSION STATE ---
if 'balance' not in st.session_state: st.session_state.balance = 0.0
if 'user' not in st.session_state: st.session_state.user = None
if 'prices' not in st.session_state:
    st.session_state.prices = {k: v['start'] for k, v in ASSETS_INFO.items()}
    
# History for Charts
if 'history' not in st.session_state:
    st.session_state.history = {}
    for sym, start in st.session_state.prices.items():
        times = [datetime.now() - timedelta(minutes=i*5) for i in range(50)]
        times.reverse()
        prices = [start]
        for _ in range(49):
            prices.append(prices[-1] * (1 + random.uniform(-0.002, 0.002)))
        st.session_state.history[sym] = {'times': times, 'prices': prices}

# PENDING ORDERS (Limit/Stop Loss)
if 'pending_orders' not in st.session_state:
    st.session_state.pending_orders = []

# --- 5. LOGIC ENGINE ---
def update_market():
    # 1. Update Prices
    for sym in st.session_state.prices:
        curr = st.session_state.prices[sym]
        move = curr * random.uniform(-0.0005, 0.0005)
        new_p = curr + move
        st.session_state.prices[sym] = new_p
        
        # Chart History
        st.session_state.history[sym]['times'].append(datetime.now())
        st.session_state.history[sym]['prices'].append(new_p)
        if len(st.session_state.history[sym]['prices']) > 60:
            st.session_state.history[sym]['prices'].pop(0)
            st.session_state.history[sym]['times'].pop(0)

    # 2. Check Pending Orders (Limit/SL)
    executed_orders = []
    for order in st.session_state.pending_orders:
        ltp = st.session_state.prices[order['Symbol']]
        trigger = False
        
        # BUY LIMIT: Execute if LTP <= Limit Price
        if order['Action'] == "BUY" and order['Type'] == "LIMIT" and ltp <= order['Price']: trigger = True
        # SELL LIMIT: Execute if LTP >= Limit Price
        elif order['Action'] == "SELL" and order['Type'] == "LIMIT" and ltp >= order['Price']: trigger = True
        # BUY SL: Execute if LTP >= Trigger Price
        elif order['Action'] == "BUY" and order['Type'] == "SL" and ltp >= order['Price']: trigger = True
        # SELL SL: Execute if LTP <= Trigger Price
        elif order['Action'] == "SELL" and order['Type'] == "SL" and ltp <= order['Price']: trigger = True
        
        if trigger:
            execute_trade(order['User'], order['Symbol'], order['Action'], order['Qty'], ltp, "EXECUTED")
            executed_orders.append(order)
            
    # Remove executed
    for ex in executed_orders:
        if ex in st.session_state.pending_orders:
            st.session_state.pending_orders.remove(ex)

def execute_trade(user, symbol, action, qty, price, status):
    # Calculate Cost
    lot = ASSETS_INFO[symbol]['lot']
    val = price * qty * lot
    cost = val + 500.0 if action == "BUY" else val - 500.0 # Brokerage
    
    # Check Funds (For Buy only)
    if action == "BUY" and st.session_state.balance < cost and status == "EXECUTED":
        return False # Fail

    # Update Balance
    if status == "EXECUTED":
        new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
        st.session_state.balance = new_bal
        update_db_balance(user, new_bal)
        update_portfolio_db(user, symbol, qty, price, action)
    
    # Log
    log_trade_db({
        'Time': datetime.now().strftime("%H:%M:%S"), 'User': user,
        'Symbol': symbol, 'Action': action, 'Qty': qty, 'Price': price, 
        'Type': status, 'Value': val
    })
    return True

update_market()

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
    try:
        ws = connect_db().worksheet("Users")
        cell = ws.find(user)
        ws.update_cell(cell.row, 3, val)
    except: pass

def log_trade_db(d):
    connect_db().worksheet("Orders").append_row(list(d.values()))

def update_portfolio_db(user, symbol, qty, price, action):
    ws = connect_db().worksheet("Portfolio")
    try:
        df = pd.DataFrame(ws.get_all_records())
        key = f"{user}_{symbol}"
        if not df.empty and key in df['User_Symbol'].values:
            idx = df.index[df['User_Symbol'] == key][0] + 2
            curr = df.iloc[idx-2]['Qty']
            new_q = curr + qty if action == "BUY" else curr - qty
            if new_q <= 0: ws.delete_rows(int(idx))
            else: ws.update_cell(int(idx), 4, int(new_q))
        elif action == "BUY":
            ws.append_row([key, user, symbol, qty, price])
    except: pass

# --- 7. LOGIN ---
if st.session_state.user is None:
    st.markdown("<br><h1 style='text-align:center; color:#ffb000; font-family:Courier New'>📦 DABBA GUL TERMINAL</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            u = st.text_input("OPERATOR ID")
            p = st.text_input("ACCESS CODE", type="password")
            if st.form_submit_button("INITIALIZE"):
                df = get_users()
                if not df.empty and u in df['Username'].values:
                    row = df[df['Username']==u].iloc[0]
                    if str(row['Password']) == str(p):
                        st.session_state.user = u
                        st.session_state.balance = float(row['Balance'])
                        st.rerun()
                    else: st.error("ACCESS DENIED")
                else: st.error("UNKNOWN ID")
    st.stop()

# --- 8. MAIN UI ---
st_autorefresh(interval=2000, key="refresh")

# SIDEBAR
with st.sidebar:
    st.markdown(f"### OPERATOR: {st.session_state.user}")
    
    st.markdown("### 📟 LIVE FEED")
    for sym, price in st.session_state.prices.items():
        change = random.uniform(-1, 1)
        color = "#00ff41" if change > 0 else "#ff3333"
        st.markdown(f"""
        <div style="border-bottom:1px dashed #444; padding:5px; display:flex; justify-content:space-between;">
            <span style="color:#ffb000">{sym}</span>
            <span style="color:{color}">{price:,.2f}</span>
        </div>
        """, unsafe_allow_html=True)
        
    if st.button("TERMINATE SESSION"):
        st.session_state.clear()
        st.rerun()

# HEADER
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown(f"<span style='color:#888'>CAPITAL</span><br><span class='big-price text-amber'>₹{st.session_state.balance:,.2f}</span>", unsafe_allow_html=True)

# WORKSPACE
col_chart, col_order = st.columns([3, 1.2])

with col_chart:
    # Asset Selector
    selected = st.selectbox("SELECT CONTRACT", list(st.session_state.prices.keys()))
    curr_price = st.session_state.prices[selected]
    
    st.markdown(f"<span class='big-price'>{curr_price:,.2f}</span> <span style='color:#00ff41'>LTP</span>", unsafe_allow_html=True)
    
    # Retro Line Chart
    data = st.session_state.history[selected]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data['times'], y=data['prices'],
        mode='lines+markers',
        line=dict(color='#ffb000', width=2),
        marker=dict(size=4, color='#000')
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1a1a1a", plot_bgcolor="#1a1a1a",
        height=450, margin=dict(t=20, b=20, l=20, r=20),
        xaxis=dict(showgrid=True, gridcolor='#333', gridwidth=1),
        yaxis=dict(showgrid=True, gridcolor='#333', gridwidth=1),
        font=dict(family="Courier New", color="#ffb000")
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with col_order:
    st.markdown("<div class='vintage-card'>", unsafe_allow_html=True)
    st.subheader("COMMAND ENTRY")
    
    with st.form("order_entry"):
        qty = st.number_input("LOTS", 1, 100, 1)
        order_type = st.radio("TYPE", ["MARKET", "LIMIT", "SL"], horizontal=True)
        limit_price = st.number_input("PRICE (For Limit/SL)", value=float(curr_price))
        
        action = st.radio("ACTION", ["BUY", "SELL"], horizontal=True)
        
        lot = ASSETS_INFO[selected]['lot']
        est_val = (limit_price if order_type != "MARKET" else curr_price) * qty * lot
        
        st.markdown("---")
        st.caption(f"REQ MARGIN: ₹{est_val:,.0f}")
        
        if st.form_submit_button("TRANSMIT ORDER"):
            if order_type == "MARKET":
                success = execute_trade(st.session_state.user, selected, action, qty, curr_price, "EXECUTED")
                if success: st.success("ORDER FILLED")
                else: st.error("INSUFFICIENT FUNDS")
            else:
                # Add to Pending
                st.session_state.pending_orders.append({
                    'User': st.session_state.user, 'Symbol': selected, 'Action': action,
                    'Qty': qty, 'Type': order_type, 'Price': limit_price
                })
                st.info(f"{order_type} ORDER QUEUED @ {limit_price}")
                
    st.markdown("</div>", unsafe_allow_html=True)

# PORTFOLIO & ORDERS
tab1, tab2 = st.tabs(["POSITIONS", "OPEN ORDERS"])

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
                    pnl = (ltp - row['Avg_Price']) * row['Qty'] * ASSETS_INFO.get(row['Symbol'], {'lot':1})['lot']
                    total_pnl += pnl
                    color = "#00ff41" if pnl >= 0 else "#ff3333"
                    rows += f"<tr><td>{row['Symbol']}</td><td>{row['Qty']}</td><td>{row['Avg_Price']}</td><td style='color:{color}'>{pnl:,.2f}</td></tr>"
                
                st.markdown(f"""
                <table style="width:100%; border:1px solid #444; font-family:Courier New; color:#ddd">
                    <tr style="border-bottom:1px solid #555; background:#222"><th>CONTRACT</th><th>QTY</th><th>AVG</th><th>P&L</th></tr>
                    {rows}
                </table>
                <div style="margin-top:10px; padding:10px; border:1px dashed #555; text-align:center">
                    NET P&L: <span style="font-size:20px; color:{'#00ff41' if total_pnl>=0 else '#ff3333'}">₹{total_pnl:,.2f}</span>
                </div>
                """, unsafe_allow_html=True)
            else: st.info("NO POSITIONS FOUND")
    except: st.error("DB ERROR")

with tab2:
    if st.session_state.pending_orders:
        orders_df = pd.DataFrame(st.session_state.pending_orders)
        st.dataframe(orders_df[['Symbol', 'Action', 'Type', 'Price', 'Qty']])
        if st.button("CANCEL ALL"):
            st.session_state.pending_orders = []
            st.rerun()
    else:
        st.info("NO PENDING ORDERS")

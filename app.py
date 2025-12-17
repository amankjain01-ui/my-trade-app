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
    page_title="Dabba Gul Pro", 
    layout="wide", 
    page_icon="📦",
    initial_sidebar_state="expanded"
)

# --- 2. THEME: ZERODHA DARK MODE ---
st.markdown("""
    <style>
        .stApp { background-color: #0e0e0e; color: #e0e0e0; }
        [data-testid="stSidebar"] { background-color: #121212; border-right: 1px solid #333; }
        .stTextInput input, .stNumberInput input, .stSelectbox div { 
            background-color: #1e1e1e !important; color: white !important; border: 1px solid #444 !important; 
        }
        .stButton button { width: 100%; border-radius: 4px; font-weight: bold; border: none; }
        .card { background-color: #1e1e1e; padding: 15px; border-radius: 8px; border: 1px solid #333; margin-bottom: 10px; }
        .metric-up { color: #2ecc71; font-weight: bold; }
        .metric-down { color: #ff5252; font-weight: bold; }
        .big-price { font-size: 36px; font-weight: bold; font-family: sans-serif; }
        
        /* Custom Table Styling */
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; color: #888; border-bottom: 1px solid #333; padding: 8px; }
        td { padding: 8px; border-bottom: 1px solid #222; }
    </style>
""", unsafe_allow_html=True)

# --- 3. SESSION STATE INITIALIZATION ---
if 'balance' not in st.session_state:
    st.session_state.balance = 0.0
if 'user' not in st.session_state:
    st.session_state.user = None

# *** EXACT PRICES FROM YOUR MCX SCREENSHOT ***
if 'prices' not in st.session_state:
    st.session_state.prices = {
        "Gold": 134278.00,      # Matched your screenshot
        "Silver": 204240.00,    # Matched your screenshot
        "Crude Oil": 5098.00,   # Matched your screenshot
        "Natural Gas": 356.70,  # Matched your screenshot
        "Copper": 1109.80,      # Matched your screenshot
        "Zinc": 303.30,         # Matched your screenshot
        "Lead": 180.60,         # Matched your screenshot
        "Nifty 50": 24145.00,   # Standard Nifty
        "Bank Nifty": 51095.00  # Standard Bank Nifty
    }

if 'history' not in st.session_state:
    st.session_state.history = {}

# --- 4. LIVE TICK ENGINE (The Heartbeat) ---
def update_prices():
    """Moves prices slightly to simulate live market"""
    for symbol in st.session_state.prices:
        current = st.session_state.prices[symbol]
        # Random tick generation (mostly noise)
        movement = current * random.uniform(-0.0003, 0.0003) 
        new_price = current + movement
        st.session_state.prices[symbol] = new_price
        
        # Save to history for chart
        if symbol not in st.session_state.history:
            st.session_state.history[symbol] = {'times': [], 'prices': []}
        
        st.session_state.history[symbol]['times'].append(datetime.now())
        st.session_state.history[symbol]['prices'].append(new_price)
        
        # Keep chart data limited to last 50 ticks
        if len(st.session_state.history[symbol]['prices']) > 100:
            st.session_state.history[symbol]['prices'].pop(0)
            st.session_state.history[symbol]['times'].pop(0)

update_prices() # Run once per reload

# --- 5. DATABASE FUNCTIONS ---
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

def update_db_balance(user, amount):
    try:
        ws = connect_db().worksheet("Users")
        cell = ws.find(user)
        ws.update_cell(cell.row, 3, amount)
    except: pass

def log_trade_db(data):
    connect_db().worksheet("Orders").append_row(list(data.values()))

def update_portfolio_db(user, symbol, qty, price, action):
    ws = connect_db().worksheet("Portfolio")
    try:
        df = pd.DataFrame(ws.get_all_records())
        key = f"{user}_{symbol}"
        if not df.empty and key in df['User_Symbol'].values:
            row_idx = df.index[df['User_Symbol'] == key][0] + 2
            curr_qty = df.iloc[row_idx-2]['Qty']
            new_qty = curr_qty + qty if action == "BUY" else curr_qty - qty
            if new_qty <= 0: ws.delete_rows(int(row_idx))
            else: ws.update_cell(int(row_idx), 4, int(new_qty))
        elif action == "BUY":
            ws.append_row([key, user, symbol, qty, price])
    except: pass

# --- 6. LOT SIZES (Standard) ---
ASSETS_INFO = {
    "Gold": 1, "Silver": 1, "Crude Oil": 100, 
    "Natural Gas": 1250, "Copper": 2500, "Zinc": 5000, "Lead": 5000,
    "Nifty 50": 50, "Bank Nifty": 15
}

# --- 7. LOGIN SCREEN ---
if st.session_state.user is None:
    st.markdown("<br><br><h1 style='text-align:center; color:#e74c3c'>📦 Dabba Gul Pro</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            u = st.text_input("User ID")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("LOGIN"):
                df = get_users()
                if not df.empty and u in df['Username'].values:
                    row = df[df['Username']==u].iloc[0]
                    if str(row['Password']) == str(p):
                        st.session_state.user = u
                        st.session_state.balance = float(row['Balance'])
                        st.rerun()
                    else: st.error("Wrong Password")
                else: st.error("User ID Invalid")
    st.stop()

# --- 8. MAIN DASHBOARD ---
st_autorefresh(interval=1000, key="data_refresh")

# --- SIDEBAR (CALIBRATION) ---
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.user}")
    
    st.info("💡 TIP: If prices are different on TV, Type the new price below to fix it.")
    
    with st.expander("⚙️ SET PRICES (Calibration)", expanded=True):
        for sym in st.session_state.prices:
            # The Admin can type the real price here if it changes
            new_val = st.number_input(f"{sym}", value=float(st.session_state.prices[sym]), step=1.0, format="%.2f")
            if abs(new_val - st.session_state.prices[sym]) > 0.01:
                st.session_state.prices[sym] = new_val

    st.markdown("---")
    st.caption("WATCHLIST")
    for sym, price in st.session_state.prices.items():
        change = random.choice(["+0.23%", "-0.10%", "+3.28%", "+0.53%"])
        color = "#2ecc71" if "+" in change else "#ff5252"
        c1, c2 = st.columns([2, 1.5])
        c1.markdown(f"**{sym}**")
        c2.markdown(f"<span style='color:{color}'>₹{price:,.0f}</span>", unsafe_allow_html=True)
    
    if st.button("LOGOUT"):
        st.session_state.clear()
        st.rerun()

# --- TOP HEADER ---
st.markdown(f"""
    <div class="card" style="display:flex; justify-content:space-between; align-items:center;">
        <div>
            <span style="color:#888">Funds</span>
            <h2 style="color:#2ecc71; margin:0">₹{st.session_state.balance:,.2f}</h2>
        </div>
        <div>
            <span style="color:#888">Status</span>
            <h4 style="color:#2ecc71; margin:0">● LIVE MARKET</h4>
        </div>
    </div>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])

with col1:
    # ASSET SELECTOR
    selected = st.selectbox("Select Asset", list(st.session_state.prices.keys()), label_visibility="collapsed")
    current_price = st.session_state.prices[selected]
    
    # BIG PRICE DISPLAY
    st.markdown(f"<div class='big-price'>₹{current_price:,.2f}</div>", unsafe_allow_html=True)
    
    # CHART
    if selected in st.session_state.history:
        data = st.session_state.history[selected]
        df_chart = pd.DataFrame({'Price': data['prices'], 'Time': data['times']})
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_chart['Time'], y=df_chart['Price'], mode='lines', 
                                 line=dict(color='#2ecc71', width=2), fill='tozeroy', fillcolor='rgba(46, 204, 113, 0.1)'))
        fig.update_layout(template="plotly_dark", paper_bgcolor="#1e1e1e", plot_bgcolor="#1e1e1e",
                          height=450, margin=dict(t=10, b=10, l=10, r=10), xaxis_showgrid=False, yaxis_showgrid=True)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with col2:
    # ORDER PANEL
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Place Order")
    with st.form("trade"):
        qty = st.number_input("Lots", 1, 100, 1)
        action = st.radio("Side", ["BUY", "SELL"], horizontal=True)
        
        lot = ASSETS_INFO.get(selected, 1)
        val = current_price * qty * lot
        
        st.markdown("---")
        st.markdown(f"**Margin:** ₹{val:,.0f}")
        st.caption(f"Lot Size: {lot} | Brokerage: ₹500")
        
        if st.form_submit_button("⚡ EXECUTE"):
            cost = val + 500.0 if action == "BUY" else val - 500.0
            if action == "BUY" and st.session_state.balance < cost:
                st.error("Insufficient Funds")
            else:
                new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
                st.session_state.balance = new_bal
                
                # Update Cloud
                update_db_balance(st.session_state.user, new_bal)
                log_trade_db({
                    'Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'User': st.session_state.user,
                    'Symbol': selected, 'Action': action, 'Qty': qty, 'Price': current_price, 'Value': val
                })
                update_portfolio_db(st.session_state.user, selected, qty, current_price, action)
                
                st.success("Trade Executed!")
                time.sleep(0.5)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# --- 9. POSITIONS ---
st.markdown("### 💼 Open Positions")
try:
    df_port = pd.DataFrame(connect_db().worksheet("Portfolio").get_all_records())
except: df_port = pd.DataFrame()

if not df_port.empty:
    my_port = df_port[df_port['User'] == st.session_state.user]
    if not my_port.empty:
        total_pnl = 0.0
        rows = ""
        for _, row in my_port.iterrows():
            ltp = st.session_state.prices.get(row['Symbol'], 0)
            pnl = (ltp - row['Avg_Price']) * row['Qty'] * ASSETS_INFO.get(row['Symbol'], 1)
            total_pnl += pnl
            
            color = "metric-up" if pnl >= 0 else "metric-down"
            rows += f"""
                <tr style="border-bottom:1px solid #333">
                    <td>{row['Symbol']}</td><td>{row['Qty']}</td><td>{row['Avg_Price']}</td><td>{ltp:,.2f}</td><td class='{color}'>{pnl:,.2f}</td>
                </tr>
            """
        
        st.markdown(f"""
            <table>
                <tr><th>Script</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&L</th></tr>
                {rows}
            </table>
            <div style="margin-top:20px; padding:15px; background:#161616; text-align:center;">
                <span style="color:#888">TOTAL P&L</span><br>
                <span style="font-size:28px" class="{'metric-up' if total_pnl>=0 else 'metric-down'}">₹{total_pnl:,.2f}</span>
            </div>
        """, unsafe_allow_html=True)
    else: st.info("No Active Trades")
else: st.info("No Active Trades")

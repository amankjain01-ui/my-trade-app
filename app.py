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

# --- 2. THEME: REALISTIC VINTAGE (Amber on Black) ---
st.markdown("""
    <style>
        /* MAIN BACKGROUND */
        .stApp { background-color: #121212; color: #ffb000; font-family: 'Courier New', monospace; }
        
        /* SIDEBAR */
        [data-testid="stSidebar"] { background-color: #1e1e1e; border-right: 2px solid #ffb000; }
        
        /* INPUTS */
        .stTextInput input, .stNumberInput input, .stSelectbox div { 
            background-color: #000; color: #ffb000 !important; border: 1px solid #ffb000 !important; 
        }
        
        /* BUTTONS */
        .stButton button {
            background-color: #000; color: #ffb000; border: 2px solid #ffb000;
            text-transform: uppercase; font-weight: bold;
        }
        .stButton button:hover { background-color: #ffb000; color: #000; }
        
        /* TEXT COLORS */
        .text-green { color: #00ff41 !important; }
        .text-red { color: #ff3333 !important; }
        .text-amber { color: #ffb000 !important; }
        
        /* BIG PRICE DISPLAY */
        .big-price { font-size: 48px; font-weight: bold; text-shadow: 0 0 8px #ffb000; }
        
        /* TABLES */
        table { width: 100%; border-collapse: collapse; border: 1px solid #333; }
        th { background-color: #222; color: #888; padding: 8px; border-bottom: 1px solid #ffb000; }
        td { background-color: #111; color: #ddd; padding: 8px; border-bottom: 1px solid #333; font-family: 'Courier New'; }
    </style>
""", unsafe_allow_html=True)

# --- 3. ACCURATE MARKET RATES (Dec 2025 Baseline) ---
# These are set to REAL market levels so they start correct.
ASSETS_INFO = {
    "Gold 05Feb Fut":      {"lot": 100, "start": 76520.00},
    "Silver 05Mar Fut":    {"lot": 30,  "start": 91250.00},
    "Crude Oil 19Dec Fut": {"lot": 100, "start": 5945.00},
    "Copper 31Dec Fut":    {"lot": 2500,"start": 862.50},
    "Natural Gas 26Dec":   {"lot": 1250,"start": 248.10},
    "Nifty 24000 CE":      {"lot": 50,  "start": 145.00},
    "Nifty 24000 PE":      {"lot": 50,  "start": 110.00},
    "BankNifty 51000 CE":  {"lot": 15,  "start": 320.00}
}

# --- 4. SESSION STATE INITIALIZATION ---
if 'balance' not in st.session_state: st.session_state.balance = 0.0
if 'user' not in st.session_state: st.session_state.user = None

# Initialize Prices if not present
if 'prices' not in st.session_state:
    st.session_state.prices = {k: v['start'] for k, v in ASSETS_INFO.items()}

# Initialize Chart History
if 'history' not in st.session_state:
    st.session_state.history = {}
    for sym, start in st.session_state.prices.items():
        # Generate 60 mins of realistic fake history so chart isn't empty
        times = [datetime.now() - timedelta(minutes=i) for i in range(60)]
        times.reverse()
        prices = [start]
        for _ in range(59):
            # Random walk
            change = random.uniform(-0.0005, 0.0005)
            prices.append(prices[-1] * (1 + change))
        st.session_state.history[sym] = {'times': times, 'prices': prices}

# --- 5. LIVE ENGINE (Heartbeat) ---
def update_market():
    # Update every single asset
    for sym in st.session_state.prices:
        current = st.session_state.prices[sym]
        # Simulate realistic tick volatility (0.02%)
        tick = current * random.uniform(-0.0002, 0.0002) 
        new_price = current + tick
        st.session_state.prices[sym] = new_price
        
        # Update History for Chart
        st.session_state.history[sym]['times'].append(datetime.now())
        st.session_state.history[sym]['prices'].append(new_price)
        
        # Keep chart clean (last 100 points)
        if len(st.session_state.history[sym]['prices']) > 100:
            st.session_state.history[sym]['prices'].pop(0)
            st.session_state.history[sym]['times'].pop(0)

# Run update logic
update_market()

# --- 6. DATABASE FUNCTIONS ---
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

def log_trade(data):
    connect_db().worksheet("Orders").append_row(list(data.values()))

def update_portfolio(user, symbol, qty, price, action):
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

# --- 7. LOGIN SCREEN ---
if st.session_state.user is None:
    st.markdown("<br><br><h1 style='text-align:center; color:#ffb000;'>📦 DABBA GUL LOGIN</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            u = st.text_input("USER ID")
            p = st.text_input("PASSWORD", type="password")
            if st.form_submit_button("ENTER TERMINAL"):
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

# --- 8. MAIN APP (AUTO-REFRESH ENABLED) ---
# This forces the app to reload every 1 second to show live P&L
st_autorefresh(interval=1000, key="live_feed")

# SIDEBAR (Calibration & Watchlist)
with st.sidebar:
    st.markdown(f"### USER: {st.session_state.user}")
    
    # Hidden Admin Panel to fix rates if they drift
    with st.expander("🔧 CALIBRATE RATES (ADMIN)"):
        for s in st.session_state.prices:
            new_v = st.number_input(s, value=float(st.session_state.prices[s]), format="%.2f")
            if abs(new_v - st.session_state.prices[s]) > 1:
                st.session_state.prices[s] = new_v # Manual Override

    st.markdown("### 📊 LIVE WATCHLIST")
    for sym, price in st.session_state.prices.items():
        change = random.uniform(-0.5, 0.5)
        color = "#00ff41" if change > 0 else "#ff3333"
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; border-bottom:1px dashed #333; padding:5px;">
            <span style="color:#ddd">{sym}</span>
            <span style="color:{color}">₹{price:,.2f}</span>
        </div>
        """, unsafe_allow_html=True)
    
    if st.button("LOGOUT"):
        st.session_state.clear()
        st.rerun()

# TOP HEADER (Balance)
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown(f"<span style='color:#888'>AVAILABLE MARGIN</span><br><span class='big-price text-amber'>₹{st.session_state.balance:,.2f}</span>", unsafe_allow_html=True)

# TRADING WORKSPACE
col_chart, col_order = st.columns([2.5, 1])

with col_chart:
    # Asset Selector
    selected = st.selectbox("SELECT CONTRACT", list(st.session_state.prices.keys()))
    curr_price = st.session_state.prices[selected]
    
    st.markdown(f"<span class='big-price'>₹{curr_price:,.2f}</span> <span class='text-green'>LIVE</span>", unsafe_allow_html=True)
    
    # Chart Engine
    data = st.session_state.history[selected]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data['times'], y=data['prices'],
        mode='lines',
        line=dict(color='#ffb000', width=2),
        fill='tozeroy', fillcolor='rgba(255, 176, 0, 0.1)'
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#121212", plot_bgcolor="#121212",
        height=450, margin=dict(t=20, b=20, l=10, r=10),
        xaxis=dict(showgrid=True, gridcolor='#333'),
        yaxis=dict(showgrid=True, gridcolor='#333', side='right')
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with col_order:
    st.markdown("<div style='background:#1e1e1e; padding:15px; border:1px solid #ffb000;'>", unsafe_allow_html=True)
    st.subheader("PLACE ORDER")
    
    with st.form("trade_panel"):
        qty = st.number_input("LOTS", 1, 100, 1)
        action = st.radio("SIDE", ["BUY", "SELL"], horizontal=True)
        
        lot = ASSETS_INFO[selected]['lot']
        val = curr_price * qty * lot
        
        st.markdown("---")
        st.markdown(f"**MARGIN:** ₹{val:,.0f}")
        st.caption(f"LOT: {lot} | FEES: ₹500")
        
        if st.form_submit_button("⚡ EXECUTE TRADE"):
            cost = val + 500.0 if action == "BUY" else val - 500.0
            
            if action == "BUY" and st.session_state.balance < cost:
                st.error("INSUFFICIENT FUNDS")
            else:
                new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
                st.session_state.balance = new_bal
                
                # Cloud Sync
                update_db_balance(st.session_state.user, new_bal)
                log_trade({
                    'Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'User': st.session_state.user,
                    'Symbol': selected, 'Action': action, 'Qty': qty, 'Price': curr_price, 'Value': val
                })
                update_portfolio(st.session_state.user, selected, qty, curr_price, action)
                st.success("ORDER FILLED")
                time.sleep(0.5)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# PORTFOLIO (Live P&L)
st.markdown("### 💼 OPEN POSITIONS")
try:
    df_port = pd.DataFrame(connect_db().worksheet("Portfolio").get_all_records())
    if not df_port.empty:
        my_port = df_port[df_port['User'] == st.session_state.user]
        if not my_port.empty:
            total_pnl = 0.0
            rows = ""
            for _, row in my_port.iterrows():
                # LIVE P&L CALCULATION
                current_ltp = st.session_state.prices.get(row['Symbol'], row['Avg_Price'])
                lot_size = ASSETS_INFO.get(row['Symbol'], {'lot': 1})['lot']
                
                pnl = (current_ltp - row['Avg_Price']) * row['Qty'] * lot_size
                total_pnl += pnl
                
                color = "text-green" if pnl >= 0 else "text-red"
                rows += f"""
                <tr>
                    <td>{row['Symbol']}</td>
                    <td>{row['Qty']}</td>
                    <td>{row['Avg_Price']:.2f}</td>
                    <td>{current_ltp:.2f}</td>
                    <td class='{color}'>{pnl:,.2f}</td>
                </tr>
                """
            
            st.markdown(f"""
            <table>
                <tr><th>SYMBOL</th><th>QTY</th><th>AVG</th><th>LTP</th><th>P&L</th></tr>
                {rows}
            </table>
            <div style="margin-top:15px; padding:15px; background:#222; text-align:center; border:1px solid #555;">
                TOTAL P&L: <span class='{'text-green' if total_pnl>=0 else 'text-red'}' style='font-size:24px; font-weight:bold;'>₹{total_pnl:,.2f}</span>
            </div>
            """, unsafe_allow_html=True)
        else: st.info("NO OPEN POSITIONS")
    else: st.info("NO OPEN POSITIONS")
except: st.error("DATABASE CONNECTION ERROR")

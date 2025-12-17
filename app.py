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
    page_title="Market Pulse Pro", 
    layout="wide", 
    page_icon="📈",
    initial_sidebar_state="expanded"
)

# --- 2. THEME: MARKET PULSE DARK MODE (Pure Black) ---
st.markdown("""
    <style>
        /* MAIN BACKGROUND */
        .stApp { background-color: #000000; color: #ffffff; }
        
        /* SIDEBAR */
        [data-testid="stSidebar"] { background-color: #121212; border-right: 1px solid #222; }
        
        /* INPUT FIELDS */
        .stTextInput input, .stNumberInput input, .stSelectbox div { 
            background-color: #1e1e1e !important; 
            color: white !important; 
            border: 1px solid #333 !important; 
            border-radius: 4px;
        }
        
        /* BUTTONS */
        .stButton button {
            background-color: #2ecc71;
            color: black;
            font-weight: bold;
            border: none;
            border-radius: 4px;
        }
        
        /* CARDS (Watchlist Style) */
        .watchlist-card {
            background-color: #111;
            padding: 10px;
            border-radius: 6px;
            border: 1px solid #333;
            margin-bottom: 8px;
            text-align: center;
        }
        
        /* TEXT COLORS */
        .text-green { color: #2ecc71; font-weight: bold; }
        .text-red { color: #ff5252; font-weight: bold; }
        .text-white { color: #ffffff; }
        .text-grey { color: #888888; font-size: 12px; }
        
        /* BIG PRICE */
        .big-price { font-size: 32px; font-weight: bold; font-family: 'Roboto', sans-serif; }
    </style>
""", unsafe_allow_html=True)

# --- 3. EXACT ASSETS FROM SCREENSHOT ---
ASSETS_INFO = {
    "Gold 05Feb":      {"lot": 100, "start": 134230.00},
    "Silver 05Mar":    {"lot": 30,  "start": 204172.00},
    "Crude Oil 18Dec": {"lot": 100, "start": 5074.00},
    "Copper 31Dec":    {"lot": 2500,"start": 1108.50},
    "Aluminium 31Dec": {"lot": 5000,"start": 280.80},
    "Zinc 31Dec":      {"lot": 5000,"start": 303.25},
    "Gold Mini 05Jan": {"lot": 10,  "start": 132605.00},
    "Silver Mini 27Feb":{"lot": 1,   "start": 204660.00},
    "USDINR":          {"lot": 1000,"start": 90.368}
}

# --- 4. SESSION STATE INITIALIZATION ---
if 'balance' not in st.session_state:
    st.session_state.balance = 0.0
if 'user' not in st.session_state:
    st.session_state.user = None
if 'prices' not in st.session_state:
    # Initialize prices with the exact values from screenshot
    st.session_state.prices = {k: v['start'] for k, v in ASSETS_INFO.items()}
    
if 'history' not in st.session_state:
    # Generate fake history so the chart isn't empty on load
    st.session_state.history = {}
    for sym, start_price in st.session_state.prices.items():
        times = [datetime.now() - timedelta(minutes=i*15) for i in range(50)]
        times.reverse()
        # Generate random walk history
        prices = [start_price]
        for _ in range(49):
            change = random.uniform(-0.001, 0.001)
            prices.append(prices[-1] * (1 + change))
        
        st.session_state.history[sym] = {'times': times, 'prices': prices}

# --- 5. LIVE TICK ENGINE ---
def update_prices():
    """Moves prices slightly to simulate live market"""
    for symbol in st.session_state.prices:
        current = st.session_state.prices[symbol]
        # Tiny movement to look alive
        movement = current * random.uniform(-0.0001, 0.0001) 
        new_price = current + movement
        st.session_state.prices[symbol] = new_price
        
        # Update Chart Data
        st.session_state.history[symbol]['times'].append(datetime.now())
        st.session_state.history[symbol]['prices'].append(new_price)
        
        # Keep only last 60 candles
        if len(st.session_state.history[symbol]['prices']) > 60:
            st.session_state.history[symbol]['prices'].pop(0)
            st.session_state.history[symbol]['times'].pop(0)

update_prices()

# --- 6. DATABASE CONNECTION ---
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

# --- 7. LOGIN SCREEN ---
if st.session_state.user is None:
    st.markdown("<br><br><h1 style='text-align:center; color:#2ecc71'>Market Pulse Pro</h1>", unsafe_allow_html=True)
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

# --- SIDEBAR: WATCHLIST ---
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.user}")
    
    # Calibration (Hidden inside expander)
    with st.expander("⚙️ Calibrate Prices"):
        for sym in st.session_state.prices:
            new_val = st.number_input(f"{sym}", value=float(st.session_state.prices[sym]))
            if abs(new_val - st.session_state.prices[sym]) > 1:
                st.session_state.prices[sym] = new_val

    st.markdown("### Watchlist")
    
    # WATCHLIST GRID (Like Screenshot)
    for sym, price in st.session_state.prices.items():
        # Fake daily change %
        change_pct = random.uniform(-0.5, 0.5)
        color_class = "text-green" if change_pct >= 0 else "text-red"
        
        st.markdown(f"""
        <div class="watchlist-card">
            <div class="text-white" style="font-weight:bold;">{sym}</div>
            <div class="text-white" style="font-size:18px;">{price:,.2f}</div>
            <div class="{color_class}" style="font-size:12px;">{change_pct:+.2f}%</div>
        </div>
        """, unsafe_allow_html=True)
    
    if st.button("LOGOUT"):
        st.session_state.clear()
        st.rerun()

# --- TOP HEADER ---
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown(f"<span style='color:#888'>Available Margin</span><br><span class='big-price text-green'>₹{st.session_state.balance:,.2f}</span>", unsafe_allow_html=True)

# --- CHARTING AREA ---
col1, col2 = st.columns([3, 1])

with col1:
    # 1. ASSET SELECTOR
    selected = st.selectbox("Select Asset", list(ASSETS_INFO.keys()))
    current_price = st.session_state.prices[selected]
    
    # 2. BIG PRICE HEADER
    st.markdown(f"<span class='big-price'>{current_price:,.2f}</span> <span style='color:#888'>LTP</span>", unsafe_allow_html=True)
    
    # 3. GENERATE CANDLES FOR CHART (Simulation)
    data = st.session_state.history[selected]
    df_chart = pd.DataFrame({'Close': data['prices'], 'Time': data['times']})
    
    # Create Open/High/Low from Close to make candles look real
    df_chart['Open'] = df_chart['Close'] * (1 + np.random.uniform(-0.0005, 0.0005, len(df_chart)))
    df_chart['High'] = df_chart[['Open', 'Close']].max(axis=1) * (1 + np.random.uniform(0, 0.0005, len(df_chart)))
    df_chart['Low'] = df_chart[['Open', 'Close']].min(axis=1) * (1 - np.random.uniform(0, 0.0005, len(df_chart)))
    
    # 4. RENDER MARKET PULSE STYLE CHART
    fig = go.Figure(data=[go.Candlestick(
        x=df_chart['Time'],
        open=df_chart['Open'], high=df_chart['High'],
        low=df_chart['Low'], close=df_chart['Close'],
        increasing_line_color='#2ecc71', # Green
        decreasing_line_color='#ff5252'  # Red
    )])
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#000000", # Pure Black
        plot_bgcolor="#000000",
        height=500,
        margin=dict(t=30, b=20, l=0, r=40),
        xaxis_rangeslider_visible=False,
        showlegend=False,
        xaxis=dict(showgrid=False), # No Gridlines (Cleaner)
        yaxis=dict(showgrid=True, gridcolor='#222', side='right') # Price on Right
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with col2:
    # 5. ORDER PANEL
    st.markdown("<div style='background-color:#111; padding:15px; border-radius:8px; border:1px solid #333;'>", unsafe_allow_html=True)
    st.subheader("Order")
    with st.form("trade"):
        qty = st.number_input("Lots", 1, 100, 1)
        action = st.radio("Action", ["BUY", "SELL"], horizontal=True)
        
        lot = ASSETS_INFO[selected]['lot']
        val = current_price * qty * lot
        
        st.markdown(f"**Margin:** ₹{val:,.0f}")
        st.caption(f"Lot: {lot} | Brokerage: ₹500")
        
        if st.form_submit_button("PLACE ORDER"):
            cost = val + 500.0 if action == "BUY" else val - 500.0
            if action == "BUY" and st.session_state.balance < cost:
                st.error("Insufficient Funds")
            else:
                new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
                st.session_state.balance = new_bal
                
                # Update DB
                update_db_balance(st.session_state.user, new_bal)
                log_trade_db({
                    'Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'User': st.session_state.user,
                    'Symbol': selected, 'Action': action, 'Qty': qty, 'Price': current_price, 'Value': val
                })
                update_portfolio_db(st.session_state.user, selected, qty, current_price, action)
                st.success("Executed")
                time.sleep(0.5)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# --- 9. PORTFOLIO TABLE ---
st.markdown("### Positions")
try:
    df_port = pd.DataFrame(connect_db().worksheet("Portfolio").get_all_records())
except: df_port = pd.DataFrame()

if not df_port.empty:
    my_port = df_port[df_port['User'] == st.session_state.user]
    if not my_port.empty:
        total_pnl = 0.0
        rows = ""
        for _, row in my_port.iterrows():
            sym = row['Symbol']
            # Fallback if symbol isn't in current asset list (e.g. old trades)
            ltp = st.session_state.prices.get(sym, row['Avg_Price'])
            
            pnl = (ltp - row['Avg_Price']) * row['Qty'] * ASSETS_INFO.get(sym, {'lot':1})['lot']
            total_pnl += pnl
            
            color = "text-green" if pnl >= 0 else "text-red"
            rows += f"""
                <tr style="border-bottom:1px solid #222;">
                    <td>{sym}</td><td>{row['Qty']}</td><td>{row['Avg_Price']}</td>
                    <td class='{color}'>{pnl:,.2f}</td>
                </tr>
            """
        
        st.markdown(f"""
            <table style="width:100%; background-color:#111;">
                <tr style="color:#888;"><th>Script</th><th>Qty</th><th>Avg</th><th>P&L</th></tr>
                {rows}
            </table>
            <div style="margin-top:10px; padding:10px; background:#111; text-align:center;">
                <span class='{ "text-green" if total_pnl>=0 else "text-red" }' style="font-size:24px; font-weight:bold;">
                    TOTAL P&L: ₹{total_pnl:,.2f}
                </span>
            </div>
        """, unsafe_allow_html=True)
